from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import CheckContext, CheckState, Diagnostic

FAILURES = frozenset(
    {
        "FAILURE",
        "ERROR",
        "TIMED_OUT",
        "CANCELLED",
        "ACTION_REQUIRED",
        "STARTUP_FAILURE",
        "STALE",
    }
)
PENDING = frozenset({"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "EXPECTED", "REQUESTED"})
PASSING = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})


def classify_all_contexts(
    contexts: Sequence[CheckContext], rollup_present: bool
) -> tuple[CheckState, Diagnostic]:
    if not rollup_present:
        return CheckState.NO_CHECKS, Diagnostic(
            "checks.no_rollup", "latest commit has no status check rollup", "rollup"
        )
    if not contexts:
        return CheckState.NO_CHECKS, Diagnostic(
            "checks.empty_rollup", "status check rollup contains no contexts", "rollup"
        )
    observed = {item.conclusion or item.status or "UNKNOWN" for item in contexts}
    if observed & FAILURES:
        return CheckState.FAILING, Diagnostic(
            "checks.failure", "at least one returned context failed", "contexts"
        )
    if observed & PENDING:
        return CheckState.PENDING, Diagnostic(
            "checks.pending", "at least one returned context is incomplete", "contexts"
        )
    unknown = observed - PASSING
    if unknown:
        names = ", ".join(sorted(unknown))
        return CheckState.UNCLASSIFIED, Diagnostic(
            "checks.unknown_state", f"unrecognized context states: {names}", "contexts"
        )
    return CheckState.PASSING, Diagnostic(
        "checks.passing", "all returned contexts completed without failure", "contexts"
    )


def classify_merge(raw: Mapping[str, object]) -> tuple[bool, Diagnostic]:
    draft = bool(raw.get("isDraft"))
    mergeable = str(raw.get("mergeable") or "UNKNOWN")
    state = str(raw.get("mergeStateStatus") or "UNKNOWN")
    blocked = draft or mergeable != "MERGEABLE" or state != "CLEAN"
    reason = f"draft={draft}; mergeable={mergeable}; mergeStateStatus={state}"
    return blocked, Diagnostic(
        "merge.blocked" if blocked else "merge.clean", reason, "pull_request"
    )
