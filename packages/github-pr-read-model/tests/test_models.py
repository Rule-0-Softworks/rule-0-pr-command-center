from collections.abc import MutableMapping
from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from r0s_pr_read_model.models import CheckContext, CheckState, Diagnostic


def test_diagnostics_are_immutable() -> None:
    diagnostic = Diagnostic(code="checks.failure", message="one context failed", source="rollup")
    with pytest.raises(FrozenInstanceError):
        diagnostic.code = "changed"  # ty: ignore[invalid-assignment]
    assert CheckState.NO_CHECKS.value == "no_checks"


def test_check_context_freezes_raw_mapping() -> None:
    raw = {"state": "queued"}
    context = CheckContext(
        kind="check_run",
        name="build",
        status="queued",
        conclusion=None,
        url=None,
        app_database_id=None,
        raw=raw,
    )

    raw["state"] = "completed"

    assert context.raw["state"] == "queued"
    with pytest.raises(TypeError):
        cast(MutableMapping[str, object], context.raw)["state"] = "failed"
