import pytest
from r0s_pr_read_model.classify import classify_all_contexts
from r0s_pr_read_model.models import (
    CheckContext,
    CheckEvidence,
    CheckEvidenceState,
    CheckState,
    Diagnostic,
)


def context(
    *,
    kind: str = "CheckRun",
    status: str | None = "COMPLETED",
    conclusion: str | None,
) -> CheckContext:
    return CheckContext(kind, "quality", status, conclusion, None, None, {})


@pytest.mark.parametrize(
    ("evidence", "expected_state", "expected_code"),
    [
        (
            CheckEvidence(CheckEvidenceState.NO_ROLLUP, ()),
            CheckState.NO_CHECKS,
            "checks.no_rollup",
        ),
        (
            CheckEvidence(CheckEvidenceState.EMPTY_ROLLUP, ()),
            CheckState.NO_CHECKS,
            "checks.empty_rollup",
        ),
        (
            CheckEvidence(
                CheckEvidenceState.UNAVAILABLE,
                (),
                Diagnostic("checks.rollup_forbidden", "denied", "check_rollup"),
            ),
            CheckState.UNKNOWN,
            "checks.rollup_forbidden",
        ),
        (
            CheckEvidence(
                CheckEvidenceState.INCOMPLETE,
                (),
                Diagnostic("checks.pagination_incomplete", "incomplete", "contexts"),
            ),
            CheckState.UNKNOWN,
            "checks.pagination_incomplete",
        ),
        (
            CheckEvidence(CheckEvidenceState.OBSERVED, (context(conclusion="SUCCESS"),)),
            CheckState.PASSING,
            "checks.passing",
        ),
        (
            CheckEvidence(CheckEvidenceState.OBSERVED, (context(conclusion="NEUTRAL"),)),
            CheckState.PASSING,
            "checks.passing",
        ),
        (
            CheckEvidence(
                CheckEvidenceState.OBSERVED,
                (context(status="IN_PROGRESS", conclusion=None),),
            ),
            CheckState.PENDING,
            "checks.pending",
        ),
        (
            CheckEvidence(CheckEvidenceState.OBSERVED, (context(conclusion="FAILURE"),)),
            CheckState.FAILING,
            "checks.failure",
        ),
        (
            CheckEvidence(CheckEvidenceState.OBSERVED, (context(conclusion="CANCELLED"),)),
            CheckState.FAILING,
            "checks.failure",
        ),
        (
            CheckEvidence(CheckEvidenceState.OBSERVED, (context(conclusion="ALIEN"),)),
            CheckState.UNCLASSIFIED,
            "checks.unknown_state",
        ),
    ],
)
def test_check_evidence_has_truthful_classification(
    evidence, expected_state, expected_code
) -> None:
    state, diagnostic = classify_all_contexts(evidence)
    assert state is expected_state
    assert diagnostic.code == expected_code
