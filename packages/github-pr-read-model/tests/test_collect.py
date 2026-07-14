from datetime import UTC, datetime

import pytest
from r0s_pr_read_model.collect import collect_snapshot


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
            return {
                "repository": {
                    "ref": {
                        "branchProtectionRule": self.branch_protection
                    }
                }
            }
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response.get("data", response)

    def rest_json(self, path):
        self.rest_paths.append(path)
        response = next(self.rest_responses, [])
        if isinstance(response, Exception):
            raise response
        return response


def test_collection_keeps_successes_and_records_repository_error(fixtures) -> None:
    client = ScriptedClient(
        [
            fixtures["repositories_page"],
            fixtures["pull_requests_page"],
            RuntimeError("repository denied"),
        ]
    )
    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))
    assert snapshot.repository_count == 2
    assert len(snapshot.pull_requests) == 1
    assert snapshot.is_complete is False
    assert snapshot.source_errors[0].repository == "Rule-0-Softworks/denied"


def test_collection_reads_every_pr_page(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    first = deepcopy(fixtures["pull_requests_page"])
    first["data"]["repository"]["pullRequests"]["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "pr-cursor",
    }
    client = ScriptedClient([repositories, first, fixtures["pull_requests_next_page"]])
    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))
    assert [pr.number for pr in snapshot.pull_requests] == [7, 8]


def test_collection_reads_every_repository_page(fixtures) -> None:
    from copy import deepcopy

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
        [first, second, fixtures["pull_requests_page"], RuntimeError("repository denied")]
    )
    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))
    assert snapshot.repository_count == 2
    assert [pr.number for pr in snapshot.pull_requests] == [7]


def test_collection_reads_every_context_page(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    first = deepcopy(fixtures["pull_requests_page"])
    connection = first["data"]["repository"]["pullRequests"]["nodes"][0]["commits"]["nodes"][0][
        "commit"
    ]["statusCheckRollup"]["contexts"]
    connection["pageInfo"] = {"hasNextPage": True, "endCursor": "context-cursor"}
    client = ScriptedClient([repositories, first, fixtures["contexts_next_page"]])
    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))
    assert [context.name for context in snapshot.pull_requests[0].contexts] == [
        "Quality Gate",
        "legacy-ci",
        "second-page",
    ]


def test_context_page_error_keeps_pr_as_unclassified(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repository_connection = repositories["organization"]["repositories"]
    repository_connection["nodes"] = repository_connection["nodes"][:1]
    first = deepcopy(fixtures["pull_requests_page"])
    contexts = first["data"]["repository"]["pullRequests"]["nodes"][0]["commits"]["nodes"][0][
        "commit"
    ]["statusCheckRollup"]["contexts"]
    contexts["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "context-cursor",
    }
    client = ScriptedClient([repositories, first, RuntimeError("context denied")])
    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))
    assert snapshot.pull_requests[0].all_context_state == "unclassified"
    assert any(
        diagnostic.code == "checks.pagination_incomplete"
        for diagnostic in snapshot.pull_requests[0].diagnostics
    )
    assert snapshot.source_errors[0].stage == "contexts:#7"


def test_collection_reconciles_cached_base_branch_requirements(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    client = ScriptedClient(
        [repositories, fixtures["pull_requests_page"]],
        [fixtures["effective_rules"]],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

    assert snapshot.pull_requests[0].required_check_state == "unknown"
    assert client.rest_paths == [
        "/repos/Rule-0-Softworks/example/rules/branches/main?per_page=100&page=1"
    ]


def test_collection_reads_all_effective_rule_pages(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    ignored_rules = [{"type": "pull_request"} for _ in range(100)]
    required_rule = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "Quality Gate"}]},
    }
    client = ScriptedClient(
        [repositories, fixtures["pull_requests_page"]],
        [ignored_rules, [required_rule]],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

    assert snapshot.pull_requests[0].required_check_state == "failing"
    assert client.rest_paths[-1].endswith("?per_page=100&page=2")


def test_collection_unions_ruleset_and_branch_protection_checks(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    pull_requests = deepcopy(fixtures["pull_requests_page"])
    commit = pull_requests["data"]["repository"]["pullRequests"]["nodes"][0]["commits"]["nodes"][0][
        "commit"
    ]
    contexts = commit["statusCheckRollup"]["contexts"]["nodes"]
    contexts[0]["conclusion"] = "SUCCESS"
    contexts[1]["conclusion"] = "FAILURE"
    effective_rules = [
        rule for rule in fixtures["effective_rules"] if rule["type"] != "merge_queue"
    ]
    client = ScriptedClient(
        [repositories, pull_requests],
        [effective_rules],
        {
            "requiresStatusChecks": True,
            "requiredStatusChecks": [{"context": "legacy-ci", "app": None}],
        },
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

    assert snapshot.pull_requests[0].required_check_state == "failing"
    assert any("query BranchProtection" in query for query, _ in client.graphql_calls)


def test_context_page_error_cannot_claim_required_checks_passing(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    first = deepcopy(fixtures["pull_requests_page"])
    commit = first["data"]["repository"]["pullRequests"]["nodes"][0]["commits"]["nodes"][0][
        "commit"
    ]
    commit["statusCheckRollup"]["contexts"]["nodes"][0]["conclusion"] = "SUCCESS"
    commit["statusCheckRollup"]["contexts"]["pageInfo"] = {
        "hasNextPage": True,
        "endCursor": "context-cursor",
    }
    client = ScriptedClient(
        [repositories, first, RuntimeError("context denied")],
        [fixtures["effective_rules"]],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

    assert snapshot.pull_requests[0].required_check_state == "unknown"
    assert all(
        diagnostic.code != "required.passing"
        for diagnostic in snapshot.pull_requests[0].diagnostics
    )


def test_malformed_pr_does_not_block_other_prs(fixtures) -> None:
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    pull_requests = deepcopy(fixtures["pull_requests_page"])
    malformed = pull_requests["data"]["repository"]["pullRequests"]["nodes"][0]
    malformed.pop("title")
    valid = deepcopy(malformed)
    valid["number"] = 8
    valid["title"] = "A valid pull request"
    pull_requests["data"]["repository"]["pullRequests"]["nodes"] = [malformed, valid]
    client = ScriptedClient([repositories, pull_requests])

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

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
    from copy import deepcopy

    repositories = deepcopy(fixtures["repositories_page"])
    repositories["organization"]["repositories"]["nodes"] = repositories["organization"][
        "repositories"
    ]["nodes"][:1]
    client = ScriptedClient(
        [repositories, fixtures["pull_requests_page"]],
        [failure],
    )

    snapshot = collect_snapshot(client, "Rule-0-Softworks", datetime(2026, 7, 14, tzinfo=UTC))

    diagnostic = next(
        item for item in snapshot.pull_requests[0].diagnostics if item.code == diagnostic_code
    )
    source_error = next(item for item in snapshot.source_errors if item.stage == "required_rules")
    assert source_error.message == diagnostic.message
    assert "secret-value" not in diagnostic.message
    assert "secret-value" not in source_error.message
