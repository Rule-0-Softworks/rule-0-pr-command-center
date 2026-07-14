import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures() -> dict[str, object]:
    directory = Path(__file__).parent / "fixtures"
    paths = directory.glob("*.json")
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in paths}


@pytest.fixture
def required_case():
    def make(case: str):
        from r0s_pr_read_model.models import CheckContext, Diagnostic, RequiredCheck
        from r0s_pr_read_model.required_checks import (
            EffectiveRequirements,
        )

        available = case != "permission_denied"
        checks = () if case == "no_rules" else (RequiredCheck("quality", 15368, "effective_rules"),)
        requirements = EffectiveRequirements(
            checks,
            False,
            available,
            Diagnostic("required.fixture", case, "test"),
        )
        state = "SUCCESS"
        if case == "one_failure":
            state = "FAILURE"
        elif case == "one_pending":
            state = "IN_PROGRESS"
        name = "other" if case == "missing_context" else "quality"
        app_id = 999 if case == "app_id_mismatch" else 15368
        kind = "StatusContext" if case == "legacy_status_with_required_app" else "CheckRun"
        status = state if state == "IN_PROGRESS" else "COMPLETED"
        conclusion = None if state == "IN_PROGRESS" else state
        contexts = [CheckContext(kind, name, status, conclusion, None, app_id, {})]
        if case == "ambiguous_duplicate_name":
            contexts.append(CheckContext("CheckRun", name, status, conclusion, None, app_id, {}))
        return requirements, tuple(contexts)

    return make
