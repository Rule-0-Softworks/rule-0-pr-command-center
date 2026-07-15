# R1 Attention-First Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an accessible attention summary and a stable, decision-first default order to the read-only PR dashboard.

**Architecture:** Add pure triage helpers to `views.py`, beside the existing filter and rendering logic. The helpers read normalized `PullRequest` state, return immutable tuples and simple counts, and are consumed only by dashboard rendering; collection, GitHub access, filters, and routes remain unchanged.

**Tech Stack:** Python 3.12+, FastAPI HTML rendering, frozen read-model dataclasses, Pytest, Ruff, and Ty.

## Global Constraints

- Keep GitHub read-only; `/refresh` remains the only local POST route.
- Do not change collection, required-check reconciliation, filter URL composition, or responsive table behavior.
- Never treat incomplete evidence as passing.
- Keep `all_context_state` and `required_check_state` distinct.
- Show every PR in the table; fully passing CI is after pending in the remaining group.
- Preserve incoming snapshot order for PRs with the same priority.
- State meaning must be communicated with text, not color alone.
- The summary always reports mutually exclusive whole-snapshot triage buckets,
  not raw facets or the currently filtered table.
- Apply the priority ladder only to the unfiltered default view; an explicit
  filter preserves the filtered snapshot order.

---

## File Structure

- Modify `src/r0s_pr_command_center/views.py`: pure tier/count helpers and summary HTML.
- Modify `src/r0s_pr_command_center/static/styles.css`: compact, neutral summary layout.
- Modify `tests/test_views.py`: priority, count, zero-copy, and rendered-order coverage.

### Task 1: Add stable triage helpers

**Files:**
- Modify: `src/r0s_pr_command_center/views.py:16-68`
- Test: `tests/test_views.py`

**Interfaces:**
- Produces: `triage_tier(pr: PullRequest) -> str`, `triage_priority(pr: PullRequest) -> int`, `order_for_triage(prs: tuple[PullRequest, ...]) -> tuple[PullRequest, ...]`, and `triage_bucket_counts(snapshot: DashboardSnapshot) -> dict[str, int]`.

- [ ] **Step 1: Write a failing ladder test**

```python
from dataclasses import replace

from r0s_pr_read_model.models import CheckState, RequiredCheckState
from r0s_pr_command_center.views import order_for_triage, triage_bucket_counts


def test_triage_order_prioritizes_attention_and_keeps_ties_stable(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing",) * 7)
    passing, failing, unknown, blocked, review, pending, same_tier = snapshot.pull_requests
    passing = replace(passing, required_check_state=RequiredCheckState.PASSING)
    blocked = replace(blocked, required_check_state=RequiredCheckState.PASSING)
    review = replace(review, required_check_state=RequiredCheckState.PASSING)
    pending = replace(pending, required_check_state=RequiredCheckState.PASSING)
    same_tier = replace(same_tier, required_check_state=RequiredCheckState.PASSING)

    ordered = order_for_triage((
        passing,
        replace(
            failing,
            all_context_state=CheckState.FAILING,
            required_check_state=RequiredCheckState.PASSING,
        ),
        replace(unknown, required_check_state=RequiredCheckState.UNKNOWN),
        replace(blocked, merge_blocked=True),
        replace(review, review_decision="REVIEW_REQUIRED"),
        replace(pending, all_context_state=CheckState.PENDING),
        same_tier,
    ))

    assert [pr.number for pr in ordered] == [2, 3, 4, 5, 6, 1, 7]
```

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/test_views.py::test_triage_order_prioritizes_attention_and_keeps_ties_stable -q`

Expected: FAIL because `order_for_triage` is not importable.

- [ ] **Step 3: Implement the smallest pure ranking API**

Add near `DashboardFilter` in `views.py`:

```python
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
```

- [ ] **Step 4: Add count coverage**

```python
def test_triage_bucket_counts_choose_the_highest_priority_state(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing",) * 3)
    passing, unknown, failing = snapshot.pull_requests
    configured = replace(
        snapshot,
        pull_requests=(
            replace(passing, required_check_state=RequiredCheckState.PASSING),
            replace(unknown, required_check_state=RequiredCheckState.UNKNOWN),
            replace(
                failing,
                all_context_state=CheckState.FAILING,
                required_check_state=RequiredCheckState.PASSING,
                merge_blocked=True,
            ),
        ),
    )

    assert triage_bucket_counts(configured) == {
        "failing": 1, "unknown_required": 1, "merge_blocked": 0,
        "review_required": 0, "pending": 0, "remaining": 1,
    }
```

- [ ] **Step 5: Verify the helper tests pass**

Run: `uv run pytest tests/test_views.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the helper behavior**

```bash
git add src/r0s_pr_command_center/views.py tests/test_views.py
git commit -m "feat(triage): prioritize actionable pull requests"
```

### Task 2: Render the summary and apply the default order

**Files:**
- Modify: `src/r0s_pr_command_center/views.py:55-93`
- Modify: `src/r0s_pr_command_center/static/styles.css:1-27`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `order_for_triage(snapshot.pull_requests)` for the default view and `triage_bucket_counts(snapshot)` for the whole-snapshot summary.
- Produces: `_triage_summary(counts: dict[str, int]) -> str` before the table.

- [ ] **Step 1: Write failing summary and table-order tests**

```python
def test_dashboard_renders_all_named_whole_snapshot_triage_buckets(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("failing", "passing", "passing", "passing", "pending"))
    failing, unknown, blocked, review, pending = snapshot.pull_requests
    html = render_dashboard(
        replace(
            snapshot,
            pull_requests=(
                replace(failing, required_check_state=RequiredCheckState.PASSING),
                replace(unknown, required_check_state=RequiredCheckState.UNKNOWN),
                replace(blocked, required_check_state=RequiredCheckState.PASSING, merge_blocked=True),
                replace(review, required_check_state=RequiredCheckState.PASSING, review_decision="REVIEW_REQUIRED"),
                replace(pending, required_check_state=RequiredCheckState.PASSING),
            ),
        ),
        DashboardFilter(),
    )

    assert "Needs attention" in html
    assert "Failing checks:</strong> 1" in html
    assert "Unknown required checks:</strong> 1" in html
    assert "Merge blocked:</strong> 1" in html
    assert "Review required:</strong> 1" in html
    assert "Pending checks:</strong> 1" in html
    assert html.index("Needs attention") < html.index("<table>")


def test_dashboard_explains_zero_count_triage_buckets(snapshot_factory) -> None:
    html = render_dashboard(snapshot_factory(states=("passing",)), DashboardFilter())

    assert "Failing checks:</strong> 0 — no pull requests" in html
    assert "Pending checks:</strong> 0 — no pull requests" in html


def test_dashboard_renders_failing_then_pending_then_passing(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing", "failing", "pending"))
    passing, failing, pending = snapshot.pull_requests
    html = render_dashboard(
        replace(
            snapshot,
            pull_requests=(
                replace(passing, required_check_state=RequiredCheckState.PASSING),
                replace(
                    failing,
                    required_check_state=RequiredCheckState.PASSING,
                ),
                replace(pending, required_check_state=RequiredCheckState.PASSING),
            ),
        ),
        DashboardFilter(),
    )

    assert html.index("#2 Example PR") < html.index("#3 Example PR") < html.index("#1 Example PR")


def test_filtered_dashboard_preserves_snapshot_order(snapshot_factory) -> None:
    snapshot = snapshot_factory(states=("passing", "failing", "pending"))
    passing, failing, pending = snapshot.pull_requests
    configured = replace(
        snapshot,
        pull_requests=(
            replace(passing, required_check_state=RequiredCheckState.PASSING),
            replace(failing, required_check_state=RequiredCheckState.PASSING),
            replace(pending, required_check_state=RequiredCheckState.PASSING),
        ),
    )

    html = render_dashboard(configured, DashboardFilter(review="NONE"))

    assert html.index("#1 Example PR") < html.index("#2 Example PR") < html.index("#3 Example PR")
```

- [ ] **Step 2: Verify rendering tests fail**

Run: `uv run pytest tests/test_views.py::test_dashboard_renders_all_named_whole_snapshot_triage_buckets tests/test_views.py::test_dashboard_explains_zero_count_triage_buckets tests/test_views.py::test_dashboard_renders_failing_then_pending_then_passing tests/test_views.py::test_filtered_dashboard_preserves_snapshot_order -q`

Expected: FAIL because the summary is absent and row order is still snapshot order.

- [ ] **Step 3: Implement summary markup and use the ordered rows**

```python
def render_dashboard(snapshot: DashboardSnapshot, selected: DashboardFilter) -> str:
    filtered = filter_prs(snapshot, selected)
    prs = order_for_triage(filtered) if selected == DashboardFilter() else filtered
    rows = "".join(_row(pr) for pr in prs)
    counts = count_facets(snapshot)
    triage = _triage_summary(triage_bucket_counts(snapshot))
    warning = ""
    if not snapshot.is_complete:
        errors = "".join(
            f"<li>{escape(error.repository or 'organization')}: {escape(error.message)}</li>"
            for error in snapshot.source_errors
        )
        warning = (
            f'<section class="warning"><h2>Completeness warning</h2><ul>{errors}</ul></section>'
        )
    return _page(
        "PR Command Center",
        f"{warning}<form method='post' action='/refresh'>"
        "<button type='submit'>Refresh snapshot</button></form>"
        f"{triage}{_facet_nav(counts)}<table><thead>{_head()}</thead><tbody>{rows}</tbody></table>",
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
```

- [ ] **Step 4: Add styling that does not encode state meaning in color**

```css
.triage-summary {
  margin-block: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid GrayText;
}
.triage-summary h2 { margin-block: 0 0.5rem; }
.triage-summary ul {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  margin: 0;
  padding-left: 1.25rem;
}
```

- [ ] **Step 5: Run the complete quality gate**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run ty check`

Expected: all commands pass.

- [ ] **Step 6: Commit the rendered experience**

```bash
git add src/r0s_pr_command_center/views.py src/r0s_pr_command_center/static/styles.css tests/test_views.py
git commit -m "feat(triage): add attention-first dashboard summary"
```

### Task 3: Verify the RUL-2127 boundary

**Files:**
- Read: `docs/superpowers/specs/2026-07-15-r1-attention-first-triage-design.md`
- Read: `src/r0s_pr_command_center/views.py`
- Read: `tests/test_views.py`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: acceptance evidence without a manual Linear status transition.

- [ ] **Step 1: Inspect only the R1 diff**

Run: `git diff origin/dev...HEAD -- src/r0s_pr_command_center/views.py src/r0s_pr_command_center/static/styles.css tests/test_views.py`

Expected: only summary, ordering, styling, and tests; no GitHub write surface or collector change.

- [ ] **Step 2: Re-run the full quality gate**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run ty check`

Expected: all commands pass.

- [ ] **Step 3: Prepare acceptance evidence**

Report the priority ladder, summary states, exact validation commands, and read-only boundary. Do not manually move RUL-2127 to In Review or Done; opening its PR controls review workflow state.

## Self-Review

- Spec coverage: Task 1 provides the fixed, stable ladder and mutually exclusive bucket counts. Task 2 puts text-based whole-snapshot summary evidence before the complete table, keeps passing CI after pending, and preserves source order for explicit filters. Task 3 verifies scope and acceptance evidence.
- Placeholder scan: no unresolved placeholders or generic test instructions remain.
- Type consistency: all helpers use existing `PullRequest`, `DashboardSnapshot`, `CheckState`, and `RequiredCheckState` types.
