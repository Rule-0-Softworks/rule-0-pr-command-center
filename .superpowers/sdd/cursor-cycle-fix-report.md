# Cursor Cycle Fix Report

## Status

Completed the final review blocker for repository, pull-request, and check-context pagination.
No `CheckEvidence` invariant changes or unrelated dependency changes were included.

## Changes

- Added bounded A -> B -> A regression tests for all three GraphQL connection loops.
- Preserved existing missing-cursor and immediate-repeat coverage.
- Added malformed-cursor coverage for non-string and empty-string values.
- Added one loop-local seen-cursor set per connection and centralized validation in
  `_continuation_cursor()`.
- Preserved data from every accepted page before reporting the existing stage-specific
  `SourceError`.
- Preserved `INCOMPLETE` evidence, unknown classifications, and the
  `checks.pagination_incomplete` diagnostic when check-context pagination cycles.

## TDD Evidence

RED command:

```text
uv run pytest -q packages/github-pr-read-model/tests/test_collect.py::test_repository_pagination_stops_on_cursor_cycle_and_keeps_accepted_pages packages/github-pr-read-model/tests/test_collect.py::test_pr_pagination_stops_on_cursor_cycle_and_keeps_accepted_pages packages/github-pr-read-model/tests/test_collect.py::test_context_pagination_stops_on_cursor_cycle_and_keeps_accepted_pages
```

Result: 3 failed. Each failure was the intentional sentinel assertion showing that the old
collector requested another page after returning to cursor A.

Malformed-cursor RED command:

```text
uv run pytest -q packages/github-pr-read-model/tests/test_collect.py::test_repository_pagination_stops_on_invalid_cursor
```

Result: 2 failed. Both failures were the intentional sentinel assertion showing that the old
collector continued with an invalid cursor.

Focused GREEN command:

```text
uv run pytest -q packages/github-pr-read-model/tests/test_collect.py -k "pagination_stops"
```

Result: 11 passed, 21 deselected.

## Verification

- `uv run pytest -q`: 103 passed, 1 upstream deprecation warning.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 28 files already formatted.
- `uv run --no-cache ty check`: passed.
- `git diff --check` and `git diff --cached --check`: passed after the report was added.

The first cached Ty attempt could not initialize the worktree's protected `.uv-cache`; the
no-cache rerun completed successfully and is the authoritative Ty result.

## Commit

Planned conventional commit message: `fix(read-model): stop pagination cursor cycles`.
