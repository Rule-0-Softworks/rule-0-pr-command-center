import json
from pathlib import Path

from r0s_pr_read_model.models import (
    CheckContext,
    CheckEvidence,
    CheckEvidenceState,
    CheckState,
    RequiredCheckState,
)
from r0s_pr_read_model.normalize import normalize_pull_request
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


def test_check_rollup_query_uses_cursor_for_context_pagination() -> None:
    assert "contexts(first: 100, after: $cursor)" in CHECK_ROLLUP
    assert "commits" not in PULL_REQUESTS
    assert "statusCheckRollup" not in PULL_REQUESTS
