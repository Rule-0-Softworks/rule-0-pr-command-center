from __future__ import annotations

from collections.abc import Mapping

from .models import CheckEvidence, CheckEvidenceState, CheckState, Diagnostic

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


def classify_all_contexts(evidence: CheckEvidence) -> tuple[CheckState, Diagnostic]:
    if evidence.state is CheckEvidenceState.UNAVAILABLE:
        return CheckState.UNKNOWN, evidence.diagnostic or Diagnostic(
            "checks.rollup_unavailable", "status check rollup could not be retrieved", "rollup"
        )
    if evidence.state is CheckEvidenceState.INCOMPLETE:
        return CheckState.UNKNOWN, evidence.diagnostic or Diagnostic(
            "checks.pagination_incomplete",
            "not every status context could be retrieved",
            "contexts",
        )
    if evidence.state is CheckEvidenceState.NO_ROLLUP:
        return CheckState.NO_CHECKS, Diagnostic(
            "checks.no_rollup", "latest commit has no status check rollup", "rollup"
        )
    if evidence.state is CheckEvidenceState.EMPTY_ROLLUP:
        return CheckState.NO_CHECKS, Diagnostic(
            "checks.empty_rollup", "status check rollup contains no contexts", "rollup"
        )
    contexts = evidence.contexts
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
