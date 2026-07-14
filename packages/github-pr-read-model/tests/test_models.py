from dataclasses import FrozenInstanceError

import pytest
from r0s_pr_read_model.models import CheckState, Diagnostic


def test_diagnostics_are_immutable() -> None:
    diagnostic = Diagnostic(code="checks.failure", message="one context failed", source="rollup")
    with pytest.raises(FrozenInstanceError):
        diagnostic.code = "changed"  # ty: ignore[invalid-assignment]
    assert CheckState.NO_CHECKS.value == "no_checks"
