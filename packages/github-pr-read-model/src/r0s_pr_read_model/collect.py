from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol, cast
from urllib.parse import quote

from .client import GraphQLIssue, GraphQLResponse
from .models import (
    CheckEvidence,
    CheckEvidenceState,
    DashboardSnapshot,
    Diagnostic,
    PullRequest,
    RequiredCheckState,
    SourceError,
)
from .normalize import check_evidence_from_rollup, normalize_pull_request
from .queries import BRANCH_PROTECTION, CHECK_ROLLUP, PULL_REQUESTS, REPOSITORIES
from .required_checks import (
    EffectiveRequirements,
    apply_required_requirements,
    extract_effective_requirements,
)


class GitHubReadClient(Protocol):
    def graphql(self, query: str, variables: dict[str, object]) -> GraphQLResponse: ...

    def rest_json(self, path: str) -> object: ...


def _connection(value: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool, str | None]:
    page = value["pageInfo"]
    return list(value["nodes"]), bool(page["hasNextPage"]), page.get("endCursor")


def _continuation_cursor(seen_cursors: set[str], next_cursor: object) -> str:
    if next_cursor is None:
        raise ValueError("pagination cursor was missing")
    if not isinstance(next_cursor, str) or not next_cursor:
        raise ValueError("pagination cursor was invalid")
    if next_cursor in seen_cursors:
        raise ValueError("pagination cursor did not advance")
    seen_cursors.add(next_cursor)
    return next_cursor


def _message(error: Exception) -> str:
    return str(error)[:300]


def _source_errors_from_issues(
    repository: str | None,
    stage: str,
    issues: tuple[GraphQLIssue, ...],
    pull_request_number: int | None = None,
) -> list[SourceError]:
    return [
        SourceError(
            repository=repository,
            stage=stage,
            message=issue.message,
            pull_request_number=pull_request_number,
            graphql_path=issue.path,
            graphql_locations=issue.locations,
        )
        for issue in issues
    ]


def collect_repositories(
    client: GitHubReadClient, organization: str
) -> tuple[list[str], list[SourceError]]:
    repositories: list[str] = []
    errors: list[SourceError] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        try:
            response = client.graphql(REPOSITORIES, {"org": organization, "cursor": cursor})
            errors.extend(_source_errors_from_issues(None, "repositories", response.errors))
            nodes, has_next, next_cursor = _connection(
                response.data["organization"]["repositories"]
            )
            repositories.extend(str(node["nameWithOwner"]) for node in nodes)
            if not has_next:
                break
            cursor = _continuation_cursor(seen_cursors, next_cursor)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            errors.append(SourceError(None, "repositories", _message(error)))
            break
    return repositories, errors


def _unavailable_check_evidence(messages: list[str]) -> CheckEvidence:
    denied = any(
        "forbidden" in message.casefold() or "denied" in message.casefold() for message in messages
    )
    if denied:
        diagnostic = Diagnostic(
            "checks.rollup_forbidden",
            "status check rollup access was denied",
            "rollup",
        )
    else:
        diagnostic = Diagnostic(
            "checks.enrichment_unavailable",
            "status check rollup enrichment was unavailable",
            "rollup",
        )
    return CheckEvidence(CheckEvidenceState.UNAVAILABLE, (), diagnostic)


def _incomplete_check_evidence(
    raw_contexts: list[dict[str, Any]], code: str, message: str, source: str
) -> CheckEvidence:
    mapped = check_evidence_from_rollup({"contexts": {"nodes": raw_contexts}})
    return CheckEvidence(
        CheckEvidenceState.INCOMPLETE,
        mapped.contexts,
        Diagnostic(code, message, source),
    )


def _check_rollup(response: GraphQLResponse) -> object:
    return response.data["repository"]["object"]["statusCheckRollup"]


def _collect_check_evidence(
    client: GitHubReadClient,
    repository: str,
    oid: str,
    pull_request_number: int,
) -> tuple[CheckEvidence, list[SourceError]]:
    owner, name = repository.split("/", 1)
    cursor: str | None = None
    seen_cursors: set[str] = set()
    variables: dict[str, object] = {
        "owner": owner,
        "name": name,
        "oid": oid,
        "cursor": cursor,
    }
    try:
        response = client.graphql(CHECK_ROLLUP, variables)
    except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable_check_evidence([str(error)]), [
            SourceError(repository, "check_rollup", _message(error), pull_request_number)
        ]

    errors = _source_errors_from_issues(
        repository,
        "check_rollup",
        response.errors,
        pull_request_number,
    )
    try:
        rollup = _check_rollup(response)
        evidence = check_evidence_from_rollup(rollup)
        if evidence.state is CheckEvidenceState.NO_ROLLUP:
            if response.errors:
                return _unavailable_check_evidence(
                    [issue.message for issue in response.errors]
                ), errors
            return evidence, errors
        if evidence.state is CheckEvidenceState.UNAVAILABLE:
            if response.errors:
                return _unavailable_check_evidence(
                    [issue.message for issue in response.errors]
                ), errors
            errors.append(
                SourceError(
                    repository,
                    "check_rollup",
                    evidence.diagnostic.message
                    if evidence.diagnostic is not None
                    else "status check rollup was unavailable",
                    pull_request_number,
                )
            )
            return evidence, errors
        rollup_data = cast(Mapping[str, Any], rollup)
        connection = cast(Mapping[str, Any], rollup_data["contexts"])
        raw_contexts, has_next, next_cursor = _connection(connection)
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        if not errors:
            errors.append(
                SourceError(repository, "check_rollup", _message(error), pull_request_number)
            )
        messages = [issue.message for issue in response.errors] or [str(error)]
        return _unavailable_check_evidence(messages), errors

    if response.errors:
        return (
            _incomplete_check_evidence(
                raw_contexts,
                "checks.rollup_partial",
                "status check rollup returned partial context evidence",
                "rollup",
            ),
            errors,
        )

    if has_next:
        try:
            cursor = _continuation_cursor(seen_cursors, next_cursor)
        except ValueError as error:
            errors.append(
                SourceError(repository, "check_contexts", _message(error), pull_request_number)
            )
            return (
                _incomplete_check_evidence(
                    raw_contexts,
                    "checks.pagination_incomplete",
                    "not every status context could be retrieved",
                    "contexts",
                ),
                errors,
            )

    while has_next:
        try:
            response = client.graphql(CHECK_ROLLUP, {**variables, "cursor": cursor})
        except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError) as error:
            errors.append(
                SourceError(repository, "check_contexts", _message(error), pull_request_number)
            )
            return (
                _incomplete_check_evidence(
                    raw_contexts,
                    "checks.pagination_incomplete",
                    "not every status context could be retrieved",
                    "contexts",
                ),
                errors,
            )

        page_errors = _source_errors_from_issues(
            repository,
            "check_contexts",
            response.errors,
            pull_request_number,
        )
        errors.extend(page_errors)
        try:
            rollup = _check_rollup(response)
            page_evidence = check_evidence_from_rollup(rollup)
            if page_evidence.state not in {
                CheckEvidenceState.OBSERVED,
                CheckEvidenceState.EMPTY_ROLLUP,
            }:
                raise ValueError("status check context page was unavailable")
            rollup_data = cast(Mapping[str, Any], rollup)
            page_contexts, has_next, next_cursor = _connection(
                cast(Mapping[str, Any], rollup_data["contexts"])
            )
            raw_contexts.extend(page_contexts)
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            if not page_errors:
                errors.append(
                    SourceError(repository, "check_contexts", _message(error), pull_request_number)
                )
            return (
                _incomplete_check_evidence(
                    raw_contexts,
                    "checks.pagination_incomplete",
                    "not every status context could be retrieved",
                    "contexts",
                ),
                errors,
            )
        if has_next:
            try:
                cursor = _continuation_cursor(seen_cursors, next_cursor)
            except ValueError as error:
                errors.append(
                    SourceError(
                        repository,
                        "check_contexts",
                        _message(error),
                        pull_request_number,
                    )
                )
                return (
                    _incomplete_check_evidence(
                        raw_contexts,
                        "checks.pagination_incomplete",
                        "not every status context could be retrieved",
                        "contexts",
                    ),
                    errors,
                )
        if response.errors:
            return (
                _incomplete_check_evidence(
                    raw_contexts,
                    "checks.pagination_incomplete",
                    "not every status context could be retrieved",
                    "contexts",
                ),
                errors,
            )

    return check_evidence_from_rollup({"contexts": {"nodes": raw_contexts}}), errors


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
) -> tuple[EffectiveRequirements, list[SourceError]]:
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
        return _unavailable_requirements(error), []
    try:
        response = client.graphql(
            BRANCH_PROTECTION,
            {"owner": owner, "name": name, "qualifiedName": f"refs/heads/{branch}"},
        )
        if response.errors:
            return _unavailable_requirements(RuntimeError(response.errors[0].message)), (
                _source_errors_from_issues(
                    f"{owner}/{name}",
                    "branch_protection",
                    response.errors,
                )
            )
        branch_protection = response.data["repository"]["ref"]["branchProtectionRule"]
    except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError) as error:
        return _unavailable_requirements(error), []
    return extract_effective_requirements(effective_rules, branch_protection), []


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
    seen_cursors: set[str] = set()
    while True:
        try:
            response = client.graphql(
                PULL_REQUESTS,
                {"owner": owner, "name": name, "cursor": cursor},
            )
            errors.extend(_source_errors_from_issues(repository, "pull_requests", response.errors))
            nodes, has_next, next_cursor = _connection(response.data["repository"]["pullRequests"])
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            errors.append(SourceError(repository, "pull_requests", _message(error)))
            break
        for raw_pr in nodes:
            try:
                pull_request_number = int(raw_pr["number"])
                oid = str(raw_pr["headRefOid"])
                evidence, check_errors = _collect_check_evidence(
                    client,
                    repository,
                    oid,
                    pull_request_number,
                )
                errors.extend(check_errors)
                pr = normalize_pull_request(repository, raw_pr, evidence)
            except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
                errors.append(
                    SourceError(
                        repository,
                        _pull_request_stage(raw_pr),
                        "pull request payload could not be normalized",
                    )
                )
                continue

            requirements = requirements_by_branch.get(pr.base_ref_name)
            if requirements is None:
                requirements, requirement_errors = _requirements_for_branch(
                    client, owner, name, pr.base_ref_name
                )
                requirements_by_branch[pr.base_ref_name] = requirements
                errors.extend(requirement_errors)
            pr, source_error = apply_required_requirements(pr, requirements)
            if evidence.state in {
                CheckEvidenceState.UNAVAILABLE,
                CheckEvidenceState.INCOMPLETE,
            }:
                pr = _mark_required_contexts_incomplete(pr)
            pull_requests.append(pr)
            if source_error is not None:
                errors.append(source_error)
        if not has_next:
            break
        try:
            cursor = _continuation_cursor(seen_cursors, next_cursor)
        except ValueError as error:
            errors.append(SourceError(repository, "pull_requests", _message(error)))
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
