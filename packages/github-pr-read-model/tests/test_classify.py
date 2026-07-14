import pytest
from r0s_pr_read_model.classify import classify_all_contexts
from r0s_pr_read_model.models import CheckContext, CheckState


def context(
    *,
    kind: str = "CheckRun",
    status: str | None = "COMPLETED",
    conclusion: str | None,
) -> CheckContext:
    return CheckContext(kind, "quality", status, conclusion, None, None, {})


@pytest.mark.parametrize(
    ("contexts", "rollup_present", "expected"),
    [
        ((), False, CheckState.NO_CHECKS),
        ((), True, CheckState.NO_CHECKS),
        ((context(conclusion="SUCCESS"),), True, CheckState.PASSING),
        ((context(conclusion="NEUTRAL"),), True, CheckState.PASSING),
        ((context(status="IN_PROGRESS", conclusion=None),), True, CheckState.PENDING),
        ((context(conclusion="FAILURE"),), True, CheckState.FAILING),
        ((context(conclusion="CANCELLED"),), True, CheckState.FAILING),
        ((context(conclusion="ALIEN"),), True, CheckState.UNCLASSIFIED),
    ],
)
def test_all_context_classification(contexts, rollup_present, expected) -> None:
    state, diagnostic = classify_all_contexts(contexts, rollup_present)
    assert state is expected
    assert diagnostic.code.startswith("checks.")
