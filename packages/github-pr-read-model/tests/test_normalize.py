import json
from pathlib import Path

from r0s_pr_read_model.models import CheckState, RequiredCheckState
from r0s_pr_read_model.normalize import normalize_pull_request


def test_normalization_preserves_source_diagnostics() -> None:
    fixture_path = Path(__file__).parent / "fixtures/pull_requests_page.json"
    fixture = json.loads(fixture_path.read_text())
    raw_pr = fixture["data"]["repository"]["pullRequests"]["nodes"][0]
    pr = normalize_pull_request("Rule-0-Softworks/example", raw_pr)
    assert pr.all_context_state is CheckState.FAILING
    assert pr.required_check_state is RequiredCheckState.UNKNOWN
    assert pr.contexts[0].raw["__typename"] == "CheckRun"
    assert pr.head_sha == "0123456789abcdef"
