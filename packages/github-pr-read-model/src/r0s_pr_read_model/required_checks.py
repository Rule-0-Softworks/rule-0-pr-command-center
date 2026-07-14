from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from .classify import FAILURES, PASSING, PENDING
from .models import (
    CheckContext,
    Diagnostic,
    PullRequest,
    RequiredCheck,
    RequiredCheckState,
    SourceError,
)


@dataclass(frozen=True)
class EffectiveRequirements:
    checks: tuple[RequiredCheck, ...]
    merge_queue_required: bool
    available: bool
    diagnostic: Diagnostic


def extract_effective_requirements(
    effective_rules: object | None, branch_protection: object | None
) -> EffectiveRequirements:
    if effective_rules is None:
        return _unavailable(
            "required.rules_unavailable",
            "effective branch rules were not returned",
        )
    if not isinstance(effective_rules, list):
        return _unavailable(
            "required.rules_malformed",
            "effective branch rules were not a list",
        )
    checks: dict[tuple[str, int | None], RequiredCheck] = {}
    merge_queue = False
    for rule in effective_rules:
        if not isinstance(rule, Mapping):
            return _unavailable(
                "required.rules_malformed",
                "an effective branch rule was not an object",
            )
        rule_type = rule.get("type")
        merge_queue = merge_queue or rule_type == "merge_queue"
        if rule_type == "required_status_checks":
            parameters = rule.get("parameters")
            if not isinstance(parameters, Mapping):
                return _unavailable(
                    "required.rules_malformed",
                    "required status checks had no parameters object",
                )
            raw_checks = parameters.get("required_status_checks")
            if not isinstance(raw_checks, list):
                return _unavailable(
                    "required.rules_malformed",
                    "required status checks were not a list",
                )
            for item in raw_checks:
                if not isinstance(item, Mapping):
                    return _unavailable(
                        "required.rules_malformed",
                        "a required status check was not an object",
                    )
                context = item.get("context")
                integration_id = item.get("integration_id")
                if not isinstance(context, str) or not context:
                    return _unavailable(
                        "required.rules_malformed",
                        "a required status check had no context name",
                    )
                if integration_id is not None and not isinstance(integration_id, int):
                    return _unavailable(
                        "required.rules_malformed",
                        f"required status check {context} had an invalid integration ID",
                    )
                required = RequiredCheck(context, integration_id, "effective_rules")
                checks[(required.context, required.integration_id)] = required
    if not checks and branch_protection is not None:
        fallback = _extract_branch_protection(branch_protection)
        if not fallback.available:
            return fallback
        checks.update({(item.context, item.integration_id): item for item in fallback.checks})
    return EffectiveRequirements(
        tuple(checks.values()),
        merge_queue,
        True,
        Diagnostic("required.rules_loaded", "effective branch rules loaded", "rules"),
    )


def _extract_branch_protection(branch_protection: object) -> EffectiveRequirements:
    if not isinstance(branch_protection, Mapping):
        return _unavailable(
            "required.rules_malformed",
            "branch protection was not an object",
        )
    requires_checks = branch_protection.get("requiresStatusChecks")
    if not isinstance(requires_checks, bool):
        return _unavailable(
            "required.rules_malformed",
            "branch protection did not declare requiresStatusChecks",
        )
    if not requires_checks:
        return EffectiveRequirements(
            (),
            False,
            True,
            Diagnostic(
                "required.branch_protection_loaded",
                "branch protection requires no status checks",
                "branch_protection",
            ),
        )
    raw_checks = branch_protection.get("requiredStatusChecks")
    if not isinstance(raw_checks, list):
        return _unavailable(
            "required.rules_malformed",
            "branch-protection required checks were not a list",
        )
    checks: list[RequiredCheck] = []
    for item in raw_checks:
        if not isinstance(item, Mapping):
            return _unavailable(
                "required.rules_malformed",
                "a branch-protection required check had no context name",
            )
        context = item.get("context")
        if not isinstance(context, str):
            return _unavailable(
                "required.rules_malformed",
                "a branch-protection required check had no context name",
            )
        app = item.get("app")
        if app is not None and not isinstance(app, Mapping):
            return _unavailable(
                "required.rules_malformed",
                f"branch-protection check {context} had an invalid app",
            )
        integration_id = app.get("databaseId") if isinstance(app, Mapping) else None
        if integration_id is not None and not isinstance(integration_id, int):
            return _unavailable(
                "required.rules_malformed",
                f"branch-protection check {context} had an invalid app ID",
            )
        checks.append(RequiredCheck(context, integration_id, "branch_protection"))
    return EffectiveRequirements(
        tuple(checks),
        False,
        True,
        Diagnostic(
            "required.branch_protection_loaded", "branch protection loaded", "branch_protection"
        ),
    )


def _unavailable(code: str, message: str) -> EffectiveRequirements:
    return EffectiveRequirements((), False, False, Diagnostic(code, message, "rules"))


def classify_required_checks(
    requirements: EffectiveRequirements, contexts: Sequence[CheckContext]
) -> tuple[RequiredCheckState, tuple[Diagnostic, ...]]:
    if not requirements.available:
        return RequiredCheckState.UNKNOWN, (requirements.diagnostic,)
    if not requirements.checks:
        return RequiredCheckState.NOT_CONFIGURED, (
            Diagnostic("required.none", "no required status checks apply", "rules"),
        )
    observed: list[str] = []
    for required in requirements.checks:
        named = [item for item in contexts if item.name == required.context]
        if required.integration_id is not None:
            named = [
                item
                for item in named
                if item.kind == "CheckRun" and item.app_database_id == required.integration_id
            ]
        if len(named) != 1:
            return RequiredCheckState.UNKNOWN, (
                Diagnostic(
                    "required.ambiguous_or_missing",
                    f"expected one matching context for {required.context}",
                    "reconciliation",
                ),
            )
        observed.append(named[0].conclusion or named[0].status or "UNKNOWN")
    values = set(observed)
    if values & FAILURES:
        return RequiredCheckState.FAILING, (
            Diagnostic("required.failure", "at least one required check failed", "reconciliation"),
        )
    if values & PENDING:
        return RequiredCheckState.PENDING, (
            Diagnostic(
                "required.pending",
                "at least one required check is incomplete",
                "reconciliation",
            ),
        )
    if values - PASSING:
        return RequiredCheckState.UNKNOWN, (
            Diagnostic(
                "required.unknown_state",
                "a required check has an unrecognized state",
                "reconciliation",
            ),
        )
    return RequiredCheckState.PASSING, (
        Diagnostic("required.passing", "all identified required checks passed", "reconciliation"),
    )


def apply_required_requirements(
    pr: PullRequest,
    requirements: EffectiveRequirements,
) -> tuple[PullRequest, SourceError | None]:
    state, diagnostics = classify_required_checks(requirements, pr.contexts)
    updated = replace(
        pr,
        required_check_state=state,
        diagnostics=(*pr.diagnostics, *diagnostics),
    )
    if requirements.available:
        return updated, None
    return updated, SourceError(
        repository=pr.repository,
        stage="required_rules",
        message=requirements.diagnostic.message,
    )
