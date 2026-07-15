# R2 Responsive PR Information Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the desktop PR inventory dense while providing an accessible stacked-card representation on narrow screens.

**Architecture:** Continue to render from `PullRequest` in `views.py`. Keep the existing table for desktop and add a semantic `ul/li/article` card-list sibling for narrow screens; CSS media queries choose one representation. Native `details/summary` holds secondary card metadata, requiring no JavaScript.

**Tech Stack:** Python 3.12+, FastAPI HTML rendering, CSS media queries, Pytest, Ruff, and Ty.

## Global Constraints

- Preserve the read-only GitHub boundary and existing route/filter behavior.
- Keep all-check and required-check state distinct.
- Cards visibly show repository, PR/title, attention state, required-check state, review state, and detail link.
- Use native `details/summary` for author, draft/base, SHA, merge information, and diagnostics.
- Desktop table remains dense; narrow cards replace horizontal table scanning below the breakpoint.
- Do not add JavaScript, a framework, or a design-system dependency.

---

### Task 1: Render desktop table and narrow-screen cards from the same PRs

**Files:**
- Modify: `src/r0s_pr_command_center/views.py:88-210`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `PullRequest`, `triage_tier(pr)`, and the existing `_row(pr)`.
- Produces: `_compact_card(pr: PullRequest) -> str` and `_compact_cards(prs: tuple[PullRequest, ...]) -> str`.

- [ ] **Step 1: Write the failing narrow-card rendering test**

```python
def test_dashboard_renders_compact_card_with_required_visible_fields(snapshot_factory) -> None:
    snapshot = snapshot_factory()
    pr = snapshot.pull_requests[0]

    html = render_dashboard(snapshot, DashboardFilter())

    assert "class='desktop-inventory'" in html
    assert "<ul class='compact-pr-list'" in html
    assert f"#{pr.number} {pr.title}" in html
    assert pr.repository in html
    assert f"Attention:</strong> {triage_tier(pr)}" in html
    assert f"Required checks:</strong> {pr.required_check_state.value}" in html
    assert f"Review:</strong> {pr.review_decision or 'NONE'}" in html
    assert f"href='/prs/Rule-0-Softworks/example/{pr.number}'" in html
    assert "<summary>More details</summary>" in html
    assert f"href='{pr.url}'" in html
    assert pr.head_sha in html
```

- [ ] **Step 2: Verify the test fails**

Run: `uv run pytest tests/test_views.py::test_dashboard_renders_compact_card_with_required_visible_fields -q`

Expected: FAIL because neither `desktop-inventory` nor `compact-pr-list` exists.

- [ ] **Step 3: Add card rendering and wrap both representations**

```python
def _compact_cards(prs: tuple[PullRequest, ...]) -> str:
    return "<ul class='compact-pr-list' aria-label='Pull request inventory'>" + "".join(
        _compact_card(pr) for pr in prs
    ) + "</ul>"


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
```

In `render_dashboard`, replace the single table fragment with:

```python
desktop = f"<table class='desktop-inventory'><thead>{_head()}</thead><tbody>{rows}</tbody></table>"
inventory = f"{desktop}{_compact_cards(prs)}"
```

and interpolate `inventory` where the table was rendered.

- [ ] **Step 3a: Update the existing summary-order assertion for the marked desktop table**

In `test_dashboard_renders_all_named_whole_snapshot_triage_buckets`, replace:

```python
assert html.index("Needs attention") < html.index("<table>")
```

with:

```python
assert html.index("Needs attention") < html.index("class='desktop-inventory'")
```

- [ ] **Step 4: Run the focused test**

Run: `uv run pytest tests/test_views.py::test_dashboard_renders_compact_card_with_required_visible_fields -q`

Expected: PASS.

- [ ] **Step 5: Commit the dual markup**

```bash
git add src/r0s_pr_command_center/views.py tests/test_views.py
git commit -m "feat(layout): render compact PR cards"
```

### Task 2: Switch representations with responsive CSS and verify the contract

**Files:**
- Modify: `src/r0s_pr_command_center/static/styles.css:1-46`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `.desktop-inventory`, `.compact-pr-list`, and `.compact-pr-card` from Task 1.
- Produces: desktop-only table and narrow-only card visibility at `48rem`.

- [ ] **Step 1: Write a failing stylesheet contract test**

```python
from pathlib import Path


def test_stylesheet_switches_from_table_to_cards_at_narrow_breakpoint() -> None:
    css = Path("src/r0s_pr_command_center/static/styles.css").read_text()

    assert ".compact-pr-list { display: none; }" in css
    assert "@media (max-width: 48rem)" in css
    assert ".desktop-inventory { display: none; }" in css
    assert ".compact-pr-list { display: grid; }" in css
    assert "table { min-width: 80rem; }" not in css
```

- [ ] **Step 2: Verify the stylesheet test fails**

Run: `uv run pytest tests/test_views.py::test_stylesheet_switches_from_table_to_cards_at_narrow_breakpoint -q`

Expected: FAIL because the compact-card rules do not exist and the table still has a narrow-screen minimum width.

- [ ] **Step 3: Implement desktop and narrow-screen rules**

```css
.compact-pr-list { display: none; list-style: none; margin: 0; padding: 0; }
.compact-pr-card { border: 1px solid GrayText; padding: 0.75rem; }
.compact-pr-card h3, .compact-pr-card p { margin-block: 0 0.5rem; }
.compact-pr-card dl { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 0.5rem; }
.compact-pr-card dt { font-weight: 700; }

@media (max-width: 48rem) {
  main { padding: 0.5rem; }
  .desktop-inventory { display: none; }
  .compact-pr-list { display: grid; gap: 0.75rem; }
}
```

Remove the existing narrow-screen `table { min-width: 80rem; }` rule.

- [ ] **Step 4: Run the complete quality gate**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run ty check`

Expected: all commands pass.

- [ ] **Step 5: Review scope and commit**

Run: `git diff origin/dev...HEAD -- src/r0s_pr_command_center/views.py src/r0s_pr_command_center/static/styles.css tests/test_views.py`

Expected: only R2 markup, responsive CSS, and tests; no GitHub writes, collector changes, or client-side dependency.

```bash
git add src/r0s_pr_command_center/views.py src/r0s_pr_command_center/static/styles.css tests/test_views.py
git commit -m "feat(layout): add responsive PR hierarchy"
```

## Self-Review

- Spec coverage: Task 1 keeps the dense table and adds cards with every required visible field plus native disclosure. Task 2 makes cards the narrow-screen representation without horizontal table scanning.
- Placeholder scan: all implementation, test, and command steps are explicit.
- Type consistency: the new helpers consume existing `PullRequest` values and reuse `triage_tier`; no model or route interface changes occur.
