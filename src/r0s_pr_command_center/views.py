from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape

from r0s_pr_read_model.models import (
    CheckEvidenceState,
    CheckState,
    DashboardSnapshot,
    PullRequest,
    RequiredCheckState,
)


@dataclass(frozen=True)
class DashboardFilter:
    check_state: str | None = None
    required_state: str | None = None
    review: str | None = None
    merge_blocked: bool | None = None


_TRIAGE_TIERS = {
    "failing": 0,
    "unknown_required": 1,
    "merge_blocked": 2,
    "review_required": 3,
    "pending": 4,
    "remaining": 5,
}


def triage_tier(pr: PullRequest) -> str:
    if pr.all_context_state is CheckState.FAILING:
        return "failing"
    if pr.required_check_state is RequiredCheckState.UNKNOWN:
        return "unknown_required"
    if pr.merge_blocked:
        return "merge_blocked"
    if pr.review_decision == "REVIEW_REQUIRED":
        return "review_required"
    if pr.all_context_state is CheckState.PENDING:
        return "pending"
    return "remaining"


def triage_priority(pr: PullRequest) -> int:
    return _TRIAGE_TIERS[triage_tier(pr)]


def order_for_triage(prs: tuple[PullRequest, ...]) -> tuple[PullRequest, ...]:
    return tuple(sorted(prs, key=triage_priority))


def triage_bucket_counts(snapshot: DashboardSnapshot) -> dict[str, int]:
    counts = {tier: 0 for tier in _TRIAGE_TIERS}
    for pr in snapshot.pull_requests:
        counts[triage_tier(pr)] += 1
    return counts


def filter_prs(snapshot: DashboardSnapshot, selected: DashboardFilter) -> tuple[PullRequest, ...]:
    return tuple(
        pr
        for pr in snapshot.pull_requests
        if (selected.check_state is None or pr.all_context_state.value == selected.check_state)
        and (
            selected.required_state is None
            or pr.required_check_state.value == selected.required_state
        )
        and (selected.review is None or (pr.review_decision or "NONE") == selected.review)
        and (selected.merge_blocked is None or pr.merge_blocked is selected.merge_blocked)
    )


def count_facets(snapshot: DashboardSnapshot) -> dict[str, dict[str, int]]:
    checks = {state.value: 0 for state in CheckState}
    checks.update(Counter(pr.all_context_state.value for pr in snapshot.pull_requests))
    required = {state.value: 0 for state in RequiredCheckState}
    required.update(Counter(pr.required_check_state.value for pr in snapshot.pull_requests))
    review = {state: 0 for state in ("APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED", "NONE")}
    review.update(Counter(pr.review_decision or "NONE" for pr in snapshot.pull_requests))
    merge = {"blocked": 0, "clean": 0}
    merge.update(
        Counter("blocked" if pr.merge_blocked else "clean" for pr in snapshot.pull_requests)
    )
    return {"checks": checks, "required": required, "review": review, "merge": merge}


def render_dashboard(snapshot: DashboardSnapshot, selected: DashboardFilter) -> str:
    filtered = filter_prs(snapshot, selected)
    prs = order_for_triage(filtered) if selected == DashboardFilter() else filtered
    rows = "".join(_row(pr) for pr in prs)
    warning = ""
    if not snapshot.is_complete:
        errors = "".join(
            f"<li>{escape(error.repository or 'organization')} {escape(error.stage)}"
            f"{f' #{error.pull_request_number}' if error.pull_request_number is not None else ''}: "
            f"{escape(error.message)}</li>"
            for error in snapshot.source_errors
        )
        warning = (
            f'<section class="warning"><h2>Completeness warning</h2><ul>{errors}</ul></section>'
        )
    counts = count_facets(snapshot)
    triage = _triage_summary(triage_bucket_counts(snapshot))
    desktop = (
        f"<table class='desktop-inventory'><thead>{_head()}</thead><tbody>{rows}</tbody></table>"
    )
    inventory = f"{desktop}{_compact_cards(prs)}"
    return _page(
        "PR Command Center",
        f"{warning}<form method='post' action='/refresh'>"
        "<button type='submit'>Refresh snapshot</button></form>"
        f"{triage}{_facet_nav(counts)}{inventory}",
    )


def render_pr_detail(pr: PullRequest) -> str:
    contexts = "".join(
        f"<li>{escape(item.name)}: {escape(item.conclusion or item.status or 'UNKNOWN')}</li>"
        for item in pr.contexts
    )
    diagnostics = "".join(
        f"<li><code>{escape(item.code)}</code> {escape(item.message)}</li>"
        for item in pr.diagnostics
    )
    contexts_heading = "Contexts (partial)" if _has_incomplete_evidence(pr) else "Contexts"
    return _page(
        f"{pr.repository} #{pr.number}",
        f"<a href='/'>Back</a><h1>{escape(pr.title)}</h1>"
        f"<dl><dt>Head SHA</dt><dd><code>{escape(pr.head_sha)}</code></dd>"
        f"<dt>All checks</dt><dd>{escape(pr.all_context_state.value)}</dd>"
        f"<dt>Required checks</dt><dd>{escape(pr.required_check_state.value)}</dd>"
        f"<dt>Check evidence</dt><dd>{escape(pr.check_evidence_state.value)}</dd></dl>"
        f"<ul>{diagnostics}</ul>"
        f"<h2>{contexts_heading}</h2><ul>{contexts}</ul>",
    )


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><link rel='stylesheet' href='/static/styles.css'>"
        f"</head><body><main>{body}</main></body></html>"
    )


def _triage_summary(counts: dict[str, int]) -> str:
    labels = (
        ("failing", "Failing checks"),
        ("unknown_required", "Unknown required checks"),
        ("merge_blocked", "Merge blocked"),
        ("review_required", "Review required"),
        ("pending", "Pending checks"),
    )
    items = "".join(
        f"<li><strong>{label}:</strong> {counts[key]}"
        + (" — no pull requests" if counts[key] == 0 else "")
        + "</li>"
        for key, label in labels
    )
    return (
        "<section class='triage-summary' aria-labelledby='triage-heading'>"
        "<h2 id='triage-heading'>Needs attention</h2><ul>"
        f"{items}</ul></section>"
    )


def _compact_cards(prs: tuple[PullRequest, ...]) -> str:
    return (
        "<ul class='compact-pr-list' aria-label='Pull request inventory'>"
        + "".join(_compact_card(pr) for pr in prs)
        + "</ul>"
    )


def _compact_card(pr: PullRequest) -> str:
    owner, repo = pr.repository.split("/", 1)
    detail = f"/prs/{escape(owner)}/{escape(repo)}/{pr.number}"
    diagnostics = "".join(
        f"<li><code>{escape(item.code)}</code> {escape(item.message)}</li>"
        for item in pr.diagnostics
    )
    return (
        "<li><article class='compact-pr-card'>"
        f"<h3>{escape(pr.repository)} <a href='{detail}'>#{pr.number} {escape(pr.title)}</a></h3>"
        f"<p><strong>Attention:</strong> {escape(triage_tier(pr))}</p>"
        f"<p><strong>Required checks:</strong> {escape(pr.required_check_state.value)}</p>"
        f"<p><strong>Check evidence:</strong> {escape(pr.check_evidence_state.value)}</p>"
        f"<p><strong>Review:</strong> {escape(pr.review_decision or 'NONE')}</p>"
        "<details><summary>More details</summary>"
        f"<dl><dt>Author</dt><dd>{escape(pr.author or 'unknown')}</dd>"
        f"<dt>Draft</dt><dd>{'yes' if pr.is_draft else 'no'}</dd>"
        f"<dt>Base</dt><dd>{escape(pr.base_ref_name)}</dd>"
        f"<dt>Head SHA</dt><dd><code>{escape(pr.head_sha)}</code></dd>"
        f"<dt>Mergeable</dt><dd>{escape(pr.mergeable)}</dd>"
        f"<dt>Merge state</dt><dd>{escape(pr.merge_state_status)}</dd></dl>"
        f"<p><a href='{escape(pr.url)}'>Open on GitHub</a></p>"
        f"<ul>{diagnostics}</ul></details></article></li>"
    )


def _facet_nav(counts: dict[str, dict[str, int]]) -> str:
    links: list[str] = []
    for value, count in sorted(counts["checks"].items()):
        links.append(f"<a href='/?check_state={escape(value)}'>{escape(value)} ({count})</a>")
    for value, count in sorted(counts["required"].items()):
        links.append(
            f"<a href='/?required_state={escape(value)}'>required {escape(value)} ({count})</a>"
        )
    for value, count in sorted(counts["review"].items()):
        links.append(f"<a href='/?review={escape(value)}'>{escape(value)} ({count})</a>")
    merge_count = counts["merge"].get("blocked", 0)
    links.append(f"<a href='/?merge_blocked=true'>merge blocked ({merge_count})</a>")
    return "<nav aria-label='Dashboard filters'>" + " ".join(links) + "</nav>"


def _head() -> str:
    labels = (
        "Repository",
        "PR",
        "Author",
        "Draft",
        "Base",
        "Head SHA",
        "Review",
        "Mergeable",
        "Merge state",
        "All checks",
        "Required checks",
        "Check evidence",
        "Diagnostics",
    )
    return "<tr>" + "".join(f"<th scope='col'>{label}</th>" for label in labels) + "</tr>"


def _row(pr: PullRequest) -> str:
    owner, repo = pr.repository.split("/", 1)
    diagnostics = "".join(
        f"<li><code>{escape(item.code)}</code> {escape(item.message)}</li>"
        for item in pr.diagnostics
    )
    detail = f"/prs/{escape(owner)}/{escape(repo)}/{pr.number}"
    values = (
        escape(pr.repository),
        f"<a href='{escape(pr.url)}'>#{pr.number} {escape(pr.title)}</a> "
        f"<a href='{detail}'>details</a>",
        escape(pr.author or "unknown"),
        "yes" if pr.is_draft else "no",
        escape(pr.base_ref_name),
        f"<code title='{escape(pr.head_sha)}'>{escape(pr.head_sha[:12])}</code>",
        escape(pr.review_decision or "NONE"),
        escape(pr.mergeable),
        escape(pr.merge_state_status),
        escape(pr.all_context_state.value),
        escape(pr.required_check_state.value),
        escape(pr.check_evidence_state.value),
        f"<details><summary>why</summary><ul>{diagnostics}</ul></details>",
    )
    return "<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>"


def _has_incomplete_evidence(pr: PullRequest) -> bool:
    return pr.check_evidence_state is CheckEvidenceState.INCOMPLETE
