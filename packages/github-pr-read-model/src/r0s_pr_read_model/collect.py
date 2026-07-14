from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from .models import CheckState, DashboardSnapshot, Diagnostic, PullRequest, SourceError
from .normalize import normalize_pull_request
from .queries import MORE_CONTEXTS, PULL_REQUESTS, REPOSITORIES


class GitHubReadClient(Protocol):
    def graphql(self, query: str, variables: dict[str, object]) -> dict[str, Any]: ...


def _connection(value: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, str | None]:
    page = value["pageInfo"]
    return list(value["nodes"]), bool(page["hasNextPage"]), page.get("endCursor")


def _message(error: Exception) -> str:
    return str(error)[:300]


def collect_repositories(
    client: GitHubReadClient, organization: str
) -> tuple[list[str], list[SourceError]]:
    repositories: list[str] = []
    errors: list[SourceError] = []
    cursor: str | None = None
    while True:
        try:
            data = client.graphql(REPOSITORIES, {"org": organization, "cursor": cursor})
            nodes, has_next, cursor = _connection(data["organization"]["repositories"])
            repositories.extend(str(node["nameWithOwner"]) for node in nodes)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            errors.append(SourceError(None, "repositories", _message(error)))
            break
        if not has_next:
            break
    return repositories, errors


def collect_remaining_contexts(
    client: GitHubReadClient, repository: str, raw_pr: dict[str, Any]
) -> list[dict[str, Any]]:
    owner, name = repository.split("/", 1)
    commit = raw_pr["commits"]["nodes"][-1]["commit"]
    connection = commit["statusCheckRollup"]["contexts"]
    contexts, has_next, cursor = _connection(connection)
    while has_next:
        data = client.graphql(
            MORE_CONTEXTS,
            {"owner": owner, "name": name, "oid": commit["oid"], "cursor": cursor},
        )
        page = data["repository"]["object"]["statusCheckRollup"]["contexts"]
        nodes, has_next, cursor = _connection(page)
        contexts.extend(nodes)
    return contexts


def _replace_contexts(raw_pr: dict[str, Any], contexts: list[dict[str, Any]]) -> None:
    connection = raw_pr["commits"]["nodes"][-1]["commit"]["statusCheckRollup"]["contexts"]
    connection["nodes"] = contexts
    connection["pageInfo"] = {"hasNextPage": False, "endCursor": None}


def _mark_incomplete(pr: PullRequest, error: Exception) -> PullRequest:
    diagnostic = Diagnostic(
        "checks.pagination_incomplete",
        f"not every status context could be retrieved: {_message(error)}",
        "contexts",
    )
    return replace(
        pr,
        all_context_state=CheckState.UNCLASSIFIED,
        diagnostics=(*pr.diagnostics, diagnostic),
    )


def collect_repository_prs(
    client: GitHubReadClient, repository: str
) -> tuple[list[PullRequest], list[SourceError]]:
    owner, name = repository.split("/", 1)
    pull_requests: list[PullRequest] = []
    errors: list[SourceError] = []
    cursor: str | None = None
    while True:
        try:
            data = client.graphql(
                PULL_REQUESTS,
                {"owner": owner, "name": name, "cursor": cursor},
            )
            nodes, has_next, cursor = _connection(data["repository"]["pullRequests"])
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            errors.append(SourceError(repository, "pull_requests", _message(error)))
            break
        for raw_pr in nodes:
            try:
                commit = raw_pr["commits"]["nodes"][-1]["commit"]
                rollup = commit.get("statusCheckRollup")
                page = rollup.get("contexts", {}).get("pageInfo", {}) if rollup else {}
                if page.get("hasNextPage"):
                    contexts = collect_remaining_contexts(client, repository, raw_pr)
                    _replace_contexts(raw_pr, contexts)
                pull_requests.append(normalize_pull_request(repository, raw_pr))
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                normalized = normalize_pull_request(repository, raw_pr)
                pull_requests.append(_mark_incomplete(normalized, error))
                errors.append(
                    SourceError(repository, f"contexts:#{raw_pr['number']}", _message(error))
                )
        if not has_next:
            break
    return pull_requests, errors


def collect_snapshot(
    client: GitHubReadClient, organization: str, now: datetime
) -> DashboardSnapshot:
    repositories, errors = collect_repositories(client, organization)
    pull_requests: list[PullRequest] = []
    for repository in repositories:
        repository_prs, repository_errors = collect_repository_prs(client, repository)
        pull_requests.extend(repository_prs)
        errors.extend(repository_errors)
    pull_requests.sort(key=lambda pr: (pr.repository.casefold(), pr.number))
    return DashboardSnapshot(
        organization=organization,
        queried_at=now,
        repository_count=len(repositories),
        pull_requests=tuple(pull_requests),
        source_errors=tuple(errors),
    )
