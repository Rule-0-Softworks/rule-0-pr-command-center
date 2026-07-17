from copy import deepcopy
from datetime import UTC, datetime

import pytest
from r0s_pr_read_model.client import GraphQLIssue, GraphQLResponse
from r0s_pr_read_model.collect import collect_snapshot
from r0s_pr_read_model.models import (
    CheckEvidenceState,
    CheckState,
    RequiredCheckState,
)

NOW = datetime(2026, 7, 14, tzinfo=UTC)
CHECK_CONTEXTS = [
    {
        "__typename": "CheckRun",
        "name": "Quality Gate",
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "detailsUrl": "https://github.com/example/check/1",
        "checkSuite": {"app": {"databaseId": 15368, "slug": "github-actions"}},
    },
    {
        "__typename": "StatusContext",
        "context": "legacy-ci",
        "state": "SUCCESS",
        "targetUrl": "https://example.invalid/legacy",
    },
]


class ScriptedClient:
    def __init__(self, responses, rest_responses=(), branch_protection=None):
        self.responses = iter(responses)
        self.rest_responses = iter(rest_responses)
        self.rest_paths = []
        self.graphql_calls = []
        self.branch_protection = branch_protection or {
            "requiresStatusChecks": False,
            "requiredStatusChecks": [],
        }

    def graphql(self, query, variables):
        self.graphql_calls.append((query, variables))
        if "query BranchProtection" in query:
            return GraphQLResponse(
                {"repository": {"ref": {"branchProtectionRule": self.branch_protection}}}
            )
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, GraphQLResponse):
            return response
        return GraphQLResponse(response.get("data", response))

    def rest_json(self, path):
        self.rest_paths.append(path)
        response = next(self.rest_responses, [])
        if isinstance(response, Exception):
            raise response
        return response


def _one_repository(fixtures):
    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    return repositories


def _inventory(fixtures):
    return deepcopy(fixtures["pull_requests_page"])


def _inventory_with_two_prs(fixtures):
    inventory = _inventory(fixtures)
    second = deepcopy(inventory["data"]["repository"]["pullRequests"]["nodes"][0])
    second.update(
        {
            "number": 8,
            "title": "Synthetic second PR",
            "url": "https://github.com/Rule-0-Softworks/example/pull/8",
            "author": {"login": "developer"},
            "headRefName": "feature/second",
            "headRefOid": "1111111111111111",
            "reviewDecision": "APPROVED",
            "mergeStateStatus": "CLEAN",
        }
    )
    inventory["data"]["repository"]["pullRequests"]["nodes"].append(second)
    return inventory


def _rollup_response(
    contexts=CHECK_CONTEXTS,
    *,
    has_next=False,
    cursor=None,
    errors=(),
):
    return GraphQLResponse(
        {
            "repository": {
                "object": {
                    "statusCheckRollup": {
                        "contexts": {
                            "pageInfo": {
                                "hasNextPage": has_next,
                                "endCursor": cursor,
                            },
                            "nodes": deepcopy(contexts),
                        }
                    }
                }
            }
        },
        tuple(errors),
    )


def _null_rollup_response():
    return GraphQLResponse(
        {"repository": {"object": {"statusCheckRollup": None}}}
    )


def _forbidden_issue(number=7):
    return GraphQLIssue(
        "Resource forbidden for token",
        (
            "repository",
            "object",
            "statusCheckRollup",
        ),
        ((7 + number, 13),),
    )


def _denied_rollup(number=7):
    return GraphQLResponse({}, (_forbidden_issue(number),))


def _diagnostic(pr, code):
    return next(item for item in pr.diagnostics if item.code == code)


def test_collection_keeps_successes_and_records_repository_error(fixtures) -> None:
    client = ScriptedClient(
        [
            fixtures["repositories_page"],
            fixtures["pull_requests_page"],
            _rollup_response(),
            RuntimeError("repository denied"),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert snapshot.repository_count == 2
    assert len(snapshot.pull_requests) == 1
    assert snapshot.is_complete is False
    assert snapshot.source_errors[0].repository == "Rule-0-Softworks/denied"


def test_collection_reads_every_pr_page(fixtures) -> None:
    first = _inventory(fixtures)
    first["data"]["repository"]["pullRequests"]["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "pr-cursor",
    }
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            first,
            _rollup_response(),
            fixtures["pull_requests_next_page"],
            _null_rollup_response(),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [pr.number for pr in snapshot.pull_requests] == [7, 8]


def test_collection_reads_every_repository_page(fixtures) -> None:
    first = deepcopy(fixtures["repositories_page"])
    first_repositories = first["organization"]["repositories"]
    first_repositories["nodes"] = first_repositories["nodes"][:1]
    first["organization"]["repositories"]["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "repository-cursor",
    }
    second = deepcopy(fixtures["repositories_page"])
    second_repositories = second["organization"]["repositories"]
    second_repositories["nodes"] = second_repositories["nodes"][1:]
    client = ScriptedClient(
        [
            first,
            second,
            fixtures["pull_requests_page"],
            _rollup_response(),
            RuntimeError("repository denied"),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert snapshot.repository_count == 2
    assert [pr.number for pr in snapshot.pull_requests] == [7]


def test_forbidden_enrichment_does_not_erase_accessible_inventory(fixtures) -> None:
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            _inventory_with_two_prs(fixtures),
            _denied_rollup(7),
            _denied_rollup(8),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [pr.number for pr in snapshot.pull_requests] == [7, 8]
    assert snapshot.pull_requests[0].check_evidence_state is CheckEvidenceState.UNAVAILABLE
    assert snapshot.pull_requests[0].all_context_state is CheckState.UNKNOWN
    assert snapshot.pull_requests[0].required_check_state is RequiredCheckState.UNKNOWN
    assert snapshot.is_complete is False
    assert snapshot.source_errors[0].stage == "check_rollup"
    assert snapshot.source_errors[0].pull_request_number == 7
    assert snapshot.source_errors[0].graphql_path[-1] == "statusCheckRollup"
    assert snapshot.source_errors[0].graphql_locations == ((14, 13),)
    assert _diagnostic(snapshot.pull_requests[0], "checks.rollup_forbidden")
    assert client.rest_paths == [
        "/repos/Rule-0-Softworks/example/rules/branches/main?per_page=100&page=1"
    ]
    assert sum("query BranchProtection" in query for query, _ in client.graphql_calls) == 1


def test_successful_pr_after_failed_enrichment_is_still_collected(fixtures) -> None:
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            _inventory_with_two_prs(fixtures),
            RuntimeError("check rollup denied"),
            _rollup_response(),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [pr.number for pr in snapshot.pull_requests] == [7, 8]
    assert snapshot.pull_requests[0].check_evidence_state is CheckEvidenceState.UNAVAILABLE
    assert snapshot.pull_requests[1].check_evidence_state is CheckEvidenceState.OBSERVED
    assert snapshot.pull_requests[1].all_context_state is CheckState.FAILING


def test_inventory_partial_response_preserves_accessible_prs(fixtures) -> None:
    issue = GraphQLIssue(
        "one inventory field was unavailable",
        ("repository", "pullRequests", "nodes", 0, "author"),
        ((10, 9),),
    )
    inventory = GraphQLResponse(fixtures["pull_requests_page"]["data"], (issue,))
    client = ScriptedClient(
        [_one_repository(fixtures), inventory, _rollup_response()]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [pr.number for pr in snapshot.pull_requests] == [7]
    assert snapshot.source_errors[0].stage == "pull_requests"
    assert snapshot.source_errors[0].graphql_path[-1] == "author"


def test_first_rollup_partial_response_keeps_contexts_without_classifying(fixtures) -> None:
    passing_context = deepcopy(CHECK_CONTEXTS[0])
    passing_context["conclusion"] = "SUCCESS"
    issue = GraphQLIssue(
        "one rollup context was denied",
        ("repository", "object", "statusCheckRollup"),
        ((18, 11),),
    )
    effective_rules = [
        rule for rule in fixtures["effective_rules"] if rule["type"] != "merge_queue"
    ]
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            _inventory(fixtures),
            _rollup_response([passing_context], errors=(issue,)),
        ],
        [effective_rules],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)
    pr = snapshot.pull_requests[0]

    assert [context.name for context in pr.contexts] == ["Quality Gate"]
    assert pr.check_evidence_state is CheckEvidenceState.INCOMPLETE
    assert pr.all_context_state is CheckState.UNKNOWN
    assert pr.required_check_state is RequiredCheckState.UNKNOWN
    assert _diagnostic(pr, "checks.rollup_partial")
    assert all(item.code != "required.passing" for item in pr.diagnostics)
    assert snapshot.source_errors[0].stage == "check_rollup"
    assert snapshot.source_errors[0].pull_request_number == 7


def test_genuine_null_rollup_is_distinct_from_unavailable(fixtures) -> None:
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _null_rollup_response()]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)
    pr = snapshot.pull_requests[0]

    assert pr.check_evidence_state is CheckEvidenceState.NO_ROLLUP
    assert pr.all_context_state is CheckState.NO_CHECKS
    assert snapshot.is_complete is True


def test_empty_rollup_is_distinct_from_unavailable(fixtures) -> None:
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _rollup_response([])]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)
    pr = snapshot.pull_requests[0]

    assert pr.check_evidence_state is CheckEvidenceState.EMPTY_ROLLUP
    assert pr.all_context_state is CheckState.NO_CHECKS
    assert snapshot.is_complete is True


def test_collection_reads_every_context_page(fixtures) -> None:
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            _inventory(fixtures),
            _rollup_response(CHECK_CONTEXTS, has_next=True, cursor="context-cursor"),
            fixtures["contexts_next_page"],
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [context.name for context in snapshot.pull_requests[0].contexts] == [
        "Quality Gate",
        "legacy-ci",
        "second-page",
    ]
    rollup_calls = [
        variables for query, variables in client.graphql_calls if "query CheckRollup" in query
    ]
    assert rollup_calls[0]["cursor"] is None
    assert rollup_calls[1]["cursor"] == "context-cursor"


def test_context_page_error_keeps_retained_contexts_as_incomplete(fixtures) -> None:
    passing_context = deepcopy(CHECK_CONTEXTS[0])
    passing_context["conclusion"] = "SUCCESS"
    effective_rules = [
        rule for rule in fixtures["effective_rules"] if rule["type"] != "merge_queue"
    ]
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            _inventory(fixtures),
            _rollup_response([passing_context], has_next=True, cursor="context-cursor"),
            RuntimeError("context denied"),
        ],
        [effective_rules],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)
    pr = snapshot.pull_requests[0]

    assert [context.name for context in pr.contexts] == ["Quality Gate"]
    assert pr.check_evidence_state is CheckEvidenceState.INCOMPLETE
    assert pr.all_context_state is CheckState.UNKNOWN
    assert pr.required_check_state is RequiredCheckState.UNKNOWN
    assert _diagnostic(pr, "checks.pagination_incomplete")
    assert all(item.code != "required.passing" for item in pr.diagnostics)
    assert snapshot.source_errors[0].stage == "check_contexts"
    assert snapshot.source_errors[0].pull_request_number == 7


def test_collection_reconciles_cached_base_branch_requirements(fixtures) -> None:
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _rollup_response()],
        [fixtures["effective_rules"]],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert snapshot.pull_requests[0].required_check_state == "unknown"
    assert client.rest_paths == [
        "/repos/Rule-0-Softworks/example/rules/branches/main?per_page=100&page=1"
    ]


def test_collection_reads_all_effective_rule_pages(fixtures) -> None:
    ignored_rules = [{"type": "pull_request"} for _ in range(100)]
    required_rule = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "Quality Gate"}]},
    }
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _rollup_response()],
        [ignored_rules, [required_rule]],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert snapshot.pull_requests[0].required_check_state == "failing"
    assert client.rest_paths[-1].endswith("?per_page=100&page=2")


def test_collection_unions_ruleset_and_branch_protection_checks(fixtures) -> None:
    contexts = deepcopy(CHECK_CONTEXTS)
    contexts[0]["conclusion"] = "SUCCESS"
    contexts[1]["state"] = "FAILURE"
    effective_rules = [
        rule for rule in fixtures["effective_rules"] if rule["type"] != "merge_queue"
    ]
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _rollup_response(contexts)],
        [effective_rules],
        {
            "requiresStatusChecks": True,
            "requiredStatusChecks": [{"context": "legacy-ci", "app": None}],
        },
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert snapshot.pull_requests[0].required_check_state == "failing"
    assert any("query BranchProtection" in query for query, _ in client.graphql_calls)


def test_malformed_pr_does_not_block_other_prs(fixtures) -> None:
    pull_requests = _inventory_with_two_prs(fixtures)
    malformed, valid = pull_requests["data"]["repository"]["pullRequests"]["nodes"]
    malformed.pop("title")
    valid["title"] = "A valid pull request"
    client = ScriptedClient(
        [
            _one_repository(fixtures),
            pull_requests,
            _rollup_response(),
            _rollup_response(),
        ]
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    assert [pr.number for pr in snapshot.pull_requests] == [8]
    assert snapshot.source_errors[0].stage == "pull_request:#7"
    assert snapshot.source_errors[0].message == "pull request payload could not be normalized"


@pytest.mark.parametrize(
    ("failure", "diagnostic_code"),
    [
        (RuntimeError("GitHub HTTP 403 for secret-value"), "required.rules_forbidden"),
        (RuntimeError("GitHub HTTP 404 for secret-value"), "required.rules_not_found"),
        (TimeoutError("secret-value"), "required.rules_timeout"),
        ({"unexpected": "mapping"}, "required.rules_malformed"),
        (RuntimeError("service unavailable: secret-value"), "required.rules_unavailable"),
    ],
)
def test_required_rule_failure_keeps_a_sanitized_specific_reason(
    fixtures, failure, diagnostic_code
) -> None:
    client = ScriptedClient(
        [_one_repository(fixtures), _inventory(fixtures), _rollup_response()],
        [failure],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", NOW)

    diagnostic = next(
        item for item in snapshot.pull_requests[0].diagnostics if item.code == diagnostic_code
    )
    source_error = next(item for item in snapshot.source_errors if item.stage == "required_rules")
    assert source_error.message == diagnostic.message
    assert "secret-value" not in diagnostic.message
    assert "secret-value" not in source_error.message
