import pytest
from r0s_pr_read_model.models import RequiredCheckState
from r0s_pr_read_model.normalize import normalize_pull_request
from r0s_pr_read_model.required_checks import (
    apply_required_requirements,
    classify_required_checks,
    extract_effective_requirements,
)


def test_extracts_effective_rule_context_and_app_identity(fixtures) -> None:
    result = extract_effective_requirements(fixtures["effective_rules"], None)
    assert result.available is True
    assert result.checks[0].context == "Quality Gate"
    assert result.checks[0].integration_id == 15368
    assert result.checks[0].source == "effective_rules"
    assert result.merge_queue_required is True


def test_extracts_legacy_branch_protection_as_fallback(fixtures) -> None:
    result = extract_effective_requirements([], fixtures["branch_protection"])
    assert result.available is True
    assert result.checks[0].context == "Quality Gate"
    assert result.checks[0].integration_id == 15368
    assert result.checks[0].source == "branch_protection"


@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": "mapping"},
        "unexpected string",
        [None],
        [{"type": "required_status_checks", "parameters": {}}],
    ],
)
def test_malformed_effective_rules_remain_unknown(payload) -> None:
    requirements = extract_effective_requirements(payload, None)
    state, diagnostics = classify_required_checks(requirements, ())
    assert requirements.available is False
    assert requirements.diagnostic.code == "required.rules_malformed"
    assert state is RequiredCheckState.UNKNOWN
    assert diagnostics == (requirements.diagnostic,)


def test_malformed_rules_emit_required_rules_source_error(fixtures) -> None:
    raw = fixtures["pull_requests_page"]["data"]["repository"]["pullRequests"]["nodes"][0]
    pr = normalize_pull_request("Rule-0-Softworks/example", raw)
    requirements = extract_effective_requirements({"unexpected": "mapping"}, None)
    updated, source_error = apply_required_requirements(pr, requirements)
    assert updated.required_check_state is RequiredCheckState.UNKNOWN
    assert source_error is not None
    assert source_error.repository == "Rule-0-Softworks/example"
    assert source_error.stage == "required_rules"


def test_merge_queue_rules_do_not_report_pr_head_checks_as_passing(fixtures) -> None:
    from copy import deepcopy

    raw = deepcopy(fixtures["pull_requests_page"]["data"]["repository"]["pullRequests"]["nodes"][0])
    raw["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][0][
        "conclusion"
    ] = "SUCCESS"
    pr = normalize_pull_request("Rule-0-Softworks/example", raw)
    requirements = extract_effective_requirements(fixtures["effective_rules"], None)

    updated, _ = apply_required_requirements(pr, requirements)

    assert updated.required_check_state is RequiredCheckState.UNKNOWN
    assert any(
        diagnostic.code == "required.merge_queue_pending" for diagnostic in updated.diagnostics
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("no_rules", RequiredCheckState.NOT_CONFIGURED),
        ("all_success", RequiredCheckState.PASSING),
        ("one_failure", RequiredCheckState.FAILING),
        ("one_pending", RequiredCheckState.PENDING),
        ("missing_context", RequiredCheckState.UNKNOWN),
        ("permission_denied", RequiredCheckState.UNKNOWN),
        ("ambiguous_duplicate_name", RequiredCheckState.UNKNOWN),
        ("app_id_mismatch", RequiredCheckState.UNKNOWN),
        ("legacy_status_with_required_app", RequiredCheckState.UNKNOWN),
    ],
)
def test_required_check_reconciliation(required_case, case, expected) -> None:
    requirements, contexts = required_case(case)
    state, diagnostics = classify_required_checks(requirements, contexts)
    assert state is expected
    assert diagnostics
