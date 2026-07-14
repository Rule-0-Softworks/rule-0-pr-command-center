from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import quote

from .models import (
    CheckState,
    DashboardSnapshot,
    Diagnostic,
    PullRequest,
    RequiredCheckState,
    SourceError,
)
from .normalize import normalize_pull_request
from .queries import BRANCH_PROTECTION, MORE_CONTEXTS, PULL_REQUESTS, REPOSITORIES
from .required_checks import (
    EffectiveRequirements,
    apply_required_requirements,
    extract_effective_requirements,
)


class GitHubReadClient(Protocol):
    def graphql(self, query: str, variables: dict[str, object]) -> dict[str, Any]: ...

    def rest_json(self, path: str) -> object: ...


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


def _pull_request_stage(raw_pr: object) -> str:
    number = raw_pr.get("number") if isinstance(raw_pr, Mapping) else None
    return f"pull_request:#{number}" if isinstance(number, int | str) else "pull_request"


def _unavailable_requirements(error: Exception) -> EffectiveRequirements:
    error_message = str(error).casefold()
    if "http 403" in error_message:
        code, message = "required.rules_forbidden", "rules endpoint access was denied (403)"
    elif "http 404" in error_message:
        code, message = "required.rules_not_found", "rules endpoint was not found (404)"
    elif isinstance(error, TimeoutError) or "timeout" in error_message:
        code, message = "required.rules_timeout", "rules endpoint timed out"
    else:
        code, message = "required.rules_unavailable", "rules endpoint was unavailable"
    return EffectiveRequirements((), False, False, Diagnostic(code, message, "rules"))


def _requirements_for_branch(
    client: GitHubReadClient,
    owner: str,
    name: str,
    branch: str,
) -> EffectiveRequirements:
    try:
        effective_rules: object = []
        page = 1
        while True:
            rules_path = (
                f"/repos/{owner}/{name}/rules/branches/{quote(branch, safe='')}"
                f"?per_page=100&page={page}"
            )
            rules = client.rest_json(rules_path)
            if not isinstance(rules, list):
                effective_rules = rules
                break
            effective_rules.extend(rules)
            if len(rules) < 100:
                break
            page += 1
    except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable_requirements(error)
    try:
        data = client.graphql(
            BRANCH_PROTECTION,
            {"owner": owner, "name": name, "qualifiedName": f"refs/heads/{branch}"},
        )
        branch_protection = data["repository"]["ref"]["branchProtectionRule"]
    except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable_requirements(error)
    return extract_effective_requirements(effective_rules, branch_protection)


def _mark_required_contexts_incomplete(pr: PullRequest) -> PullRequest:
    return replace(
        pr,
        required_check_state=RequiredCheckState.UNKNOWN,
        diagnostics=(
            *(diagnostic for diagnostic in pr.diagnostics if diagnostic.code != "required.passing"),
            Diagnostic(
                "required.contexts_incomplete",
                "required checks cannot be reconciled because context retrieval was incomplete",
                "contexts",
            ),
        ),
    )


def collect_repository_prs(
    client: GitHubReadClient, repository: str
) -> tuple[list[PullRequest], list[SourceError]]:
    owner, name = repository.split("/", 1)
    pull_requests: list[PullRequest] = []
    errors: list[SourceError] = []
    requirements_by_branch: dict[str, EffectiveRequirements] = {}
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
            contexts_complete = True
            context_error: Exception | None = None
            try:
                commit = raw_pr["commits"]["nodes"][-1]["commit"]
                rollup = commit.get("statusCheckRollup")
                page = rollup.get("contexts", {}).get("pageInfo", {}) if rollup else {}
                if page.get("hasNextPage"):
                    contexts = collect_remaining_contexts(client, repository, raw_pr)
                    _replace_contexts(raw_pr, contexts)
            except (KeyError, TypeError, ValueError, RuntimeError) as error:
                context_error = error

            try:
                pr = normalize_pull_request(repository, raw_pr)
            except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
                errors.append(
                    SourceError(
                        repository,
                        _pull_request_stage(raw_pr),
                        "pull request payload could not be normalized",
                    )
                )
                continue

            if context_error is not None:
                pr = _mark_incomplete(pr, context_error)
                contexts_complete = False
                errors.append(
                    SourceError(
                        repository,
                        f"contexts:#{pr.number}",
                        _message(context_error),
                    )
                )
            requirements = requirements_by_branch.get(pr.base_ref_name)
            if requirements is None:
                requirements = _requirements_for_branch(client, owner, name, pr.base_ref_name)
                requirements_by_branch[pr.base_ref_name] = requirements
            pr, source_error = apply_required_requirements(pr, requirements)
            if not contexts_complete:
                pr = _mark_required_contexts_incomplete(pr)
            pull_requests.append(pr)
            if source_error is not None:
                errors.append(source_error)
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
