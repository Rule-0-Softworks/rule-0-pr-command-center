from datetime import UTC, datetime

from r0s_pr_read_model.collect import collect_snapshot


class ScriptedClient:
    def __init__(self, responses, rest_responses=()):
        self.responses = iter(responses)
        self.rest_responses = iter(rest_responses)
        self.rest_paths = []

    def graphql(self, query, variables):
        if "query BranchProtection" in query:
            return {
                "repository": {
                    "ref": {
                        "branchProtectionRule": {
                            "requiresStatusChecks": False,
                            "requiredStatusChecks": [],
                        }
                    }
                }
            }
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response.get("data", response)

    def rest_json(self, path):
        self.rest_paths.append(path)
        return next(self.rest_responses, [])


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

    assert snapshot.pull_requests[0].required_check_state == "failing"
    assert client.rest_paths == ["/repos/Rule-0-Softworks/example/rules/branches/main"]


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
