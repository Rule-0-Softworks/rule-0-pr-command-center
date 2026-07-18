import json
from pathlib import Path

import pytest
from r0s_pr_read_model.models import (
    CheckContext,
    CheckEvidence,
    CheckEvidenceState,
    CheckState,
    RequiredCheckState,
)
from r0s_pr_read_model.normalize import check_evidence_from_rollup, normalize_pull_request
from r0s_pr_read_model.queries import CHECK_ROLLUP, PULL_REQUESTS


def test_normalization_uses_observed_evidence_for_contexts_and_classification() -> None:
    fixture_path = Path(__file__).parent / "fixtures/pull_requests_page.json"
    fixture = json.loads(fixture_path.read_text())
    raw_pr = fixture["data"]["repository"]["pullRequests"]["nodes"][0]
    evidence = CheckEvidence(
        CheckEvidenceState.OBSERVED,
        (
            CheckContext(
                "CheckRun",
                "Quality Gate",
                "COMPLETED",
                "FAILURE",
                "https://github.com/example/check/1",
                15368,
                {"__typename": "CheckRun"},
            ),
            CheckContext(
                "StatusContext",
                "legacy-ci",
                None,
                "SUCCESS",
                "https://example.invalid/legacy",
                None,
                {"__typename": "StatusContext"},
            ),
        ),
    )
    pr = normalize_pull_request("Rule-0-Softworks/example", raw_pr, evidence)
    assert pr.all_context_state is CheckState.FAILING
    assert pr.required_check_state is RequiredCheckState.UNKNOWN
    assert pr.contexts[0].raw["__typename"] == "CheckRun"
    assert pr.head_sha == "0123456789abcdef"


def test_raw_rollup_evidence_preserves_check_fields_and_failing_normalization() -> None:
    fixture_path = Path(__file__).parent / "fixtures/pull_requests_page.json"
    fixture = json.loads(fixture_path.read_text())
    raw_pr = fixture["data"]["repository"]["pullRequests"]["nodes"][0]
    raw_rollup = raw_pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]

    evidence = check_evidence_from_rollup(raw_rollup)
    pr = normalize_pull_request("Rule-0-Softworks/example", raw_pr, evidence)

    assert evidence.state is CheckEvidenceState.OBSERVED
    assert evidence.contexts[0].kind == "CheckRun"
    assert evidence.contexts[0].name == "Quality Gate"
    assert evidence.contexts[0].status == "COMPLETED"
    assert evidence.contexts[0].conclusion == "FAILURE"
    assert evidence.contexts[0].url == "https://github.com/example/check/1"
    assert evidence.contexts[0].app_database_id == 15368
    assert evidence.contexts[1].kind == "StatusContext"
    assert evidence.contexts[1].name == "legacy-ci"
    assert evidence.contexts[1].conclusion == "SUCCESS"
    assert evidence.contexts[1].url == "https://example.invalid/legacy"
    assert pr.all_context_state is CheckState.FAILING


@pytest.mark.parametrize(
    "rollup",
    [
        {},
        {"contexts": {}},
        {"contexts": {"nodes": None}},
        {"contexts": {"nodes": [None]}},
    ],
)
def test_malformed_rollup_evidence_is_unavailable_not_empty(rollup: object) -> None:
    evidence = check_evidence_from_rollup(rollup)

    assert evidence.state is CheckEvidenceState.UNAVAILABLE
    assert evidence.contexts == ()
    assert evidence.diagnostic is not None
    assert evidence.diagnostic.code == "checks.rollup_malformed"


def test_empty_rollup_evidence_requires_an_actual_empty_node_list() -> None:
    evidence = check_evidence_from_rollup({"contexts": {"nodes": []}})

    assert evidence.state is CheckEvidenceState.EMPTY_ROLLUP
    assert evidence.contexts == ()


def test_check_rollup_query_uses_cursor_for_context_pagination() -> None:
    assert "contexts(first: 100, after: $cursor)" in CHECK_ROLLUP
    assert "commits" not in PULL_REQUESTS
    assert "statusCheckRollup" not in PULL_REQUESTS
