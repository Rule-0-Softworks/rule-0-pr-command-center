from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .classify import classify_all_contexts, classify_merge
from .models import (
    CheckContext,
    CheckEvidence,
    CheckEvidenceState,
    Diagnostic,
    PullRequest,
    RequiredCheckState,
)


def _object_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return cast(Mapping[str, object], value)


def _context(raw: Mapping[str, object]) -> CheckContext:
    kind = str(raw["__typename"])
    suite = raw.get("checkSuite")
    app = suite.get("app") if isinstance(suite, Mapping) else None
    app_id = app.get("databaseId") if isinstance(app, Mapping) else None
    return CheckContext(
        kind=kind,
        name=str(raw.get("name") or raw.get("context") or ""),
        status=str(raw["status"]) if raw.get("status") is not None else None,
        conclusion=str(raw.get("conclusion") or raw.get("state"))
        if raw.get("conclusion") or raw.get("state")
        else None,
        url=str(raw.get("detailsUrl") or raw.get("targetUrl"))
        if raw.get("detailsUrl") or raw.get("targetUrl")
        else None,
        app_database_id=int(app_id) if isinstance(app_id, int) else None,
        raw=dict(raw),
    )


def check_evidence_from_rollup(rollup: object) -> CheckEvidence:
    if rollup is None:
        return CheckEvidence(CheckEvidenceState.NO_ROLLUP, ())
    if not isinstance(rollup, Mapping):
        return CheckEvidence(
            CheckEvidenceState.UNAVAILABLE,
            (),
            Diagnostic("checks.rollup_malformed", "status check rollup was malformed", "rollup"),
        )
    contexts_connection = rollup.get("contexts") if isinstance(rollup, Mapping) else None
    raw_context_nodes = (
        contexts_connection.get("nodes", []) if isinstance(contexts_connection, Mapping) else []
    )
    raw_contexts = raw_context_nodes if isinstance(raw_context_nodes, list) else []
    contexts = tuple(
        _context(context) for item in raw_contexts if (context := _object_mapping(item)) is not None
    )
    return CheckEvidence(
        CheckEvidenceState.OBSERVED if contexts else CheckEvidenceState.EMPTY_ROLLUP,
        contexts,
    )


def normalize_pull_request(
    repository: str, raw: Mapping[str, object], evidence: CheckEvidence
) -> PullRequest:
    check_state, check_diagnostic = classify_all_contexts(evidence)
    merge_blocked, merge_diagnostic = classify_merge(raw)
    author = raw.get("author")
    number = raw["number"]
    if not isinstance(number, int | str):
        raise TypeError("pull request number must be an integer or string")
    return PullRequest(
        repository=repository,
        number=int(number),
        title=str(raw["title"]),
        url=str(raw["url"]),
        author=str(author.get("login"))
        if isinstance(author, Mapping) and author.get("login")
        else None,
        is_draft=bool(raw.get("isDraft")),
        base_ref_name=str(raw["baseRefName"]),
        head_ref_name=str(raw.get("headRefName") or ""),
        head_sha=str(raw["headRefOid"]),
        review_decision=str(raw["reviewDecision"]) if raw.get("reviewDecision") else None,
        mergeable=str(raw.get("mergeable") or "UNKNOWN"),
        merge_state_status=str(raw.get("mergeStateStatus") or "UNKNOWN"),
        contexts=evidence.contexts,
        check_evidence_state=evidence.state,
        all_context_state=check_state,
        required_check_state=RequiredCheckState.UNKNOWN,
        merge_blocked=merge_blocked,
        diagnostics=(check_diagnostic, merge_diagnostic),
    )
