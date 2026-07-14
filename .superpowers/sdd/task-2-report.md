# Task 2 report: dashboard contracts

## Scope

Implemented only Task 2: credential settings, immutable read-model contracts, and the two shared test fixture modules. No GitHub client, requirement-classification implementation, persistence, scheduling, mutations, or production dependencies were added.

## TDD evidence

### RED

Created these failing tests before the production modules:

- `tests/test_settings.py`
- `packages/github-pr-read-model/tests/test_models.py`

Command run:

```powershell
uv run pytest tests/test_settings.py packages/github-pr-read-model/tests/test_models.py -q
```

Result: failed during collection exactly because `r0s_pr_command_center.settings` and `r0s_pr_read_model.models` did not exist (`ModuleNotFoundError` for both modules).

### GREEN

Implemented the minimum specified contracts:

- `Settings.from_environment()` prefers `GITHUB_TOKEN`, falls back to `GH_TOKEN`, defaults the organization to `Rule-0-Softworks`, and excludes the credential from `repr`.
- `CheckState`, `RequiredCheckState`, `Diagnostic`, `CheckContext`, `RequiredCheck`, `PullRequest`, `SourceError`, and `DashboardSnapshot` are frozen dataclasses/enums as specified.
- `DashboardSnapshot.is_complete` is derived from source errors.
- Added the root `snapshot_factory` and read-model fixture/required-case builders for later tasks.

Focused verification command run:

```powershell
uv run pytest tests/test_settings.py packages/github-pr-read-model/tests/test_models.py -q
```

Result: `3 passed`.

## Quality gate

Command run:

```powershell
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

Result: passed (`All checks passed!`; `10 files already formatted`; `All checks passed!`).

## Files changed

- `src/r0s_pr_command_center/settings.py`
- `tests/test_settings.py`
- `tests/conftest.py`
- `packages/github-pr-read-model/src/r0s_pr_read_model/models.py`
- `packages/github-pr-read-model/tests/test_models.py`
- `packages/github-pr-read-model/tests/conftest.py`

## Self-review

- Verified the credential field is `repr=False`; no real credential is written to source or this report.
- Verified token precedence and missing-credential guidance are covered by the new settings tests.
- Verified immutability and the `no_checks` enum value are covered by the new model test.
- `required_case` intentionally references the Task 3 `required_checks` contract lazily. Its `ty` suppression is limited to that unavailable future module, so Task 2's type gate remains meaningful.
- Reviewed with `git diff --check`; no whitespace errors were reported.

## Concerns

The focused pytest command passes but emits one `PytestCacheWarning`: the pre-existing `.pytest_cache/v/cache` path is inaccessible in this workspace. Read-only inspection confirmed access is denied; no deletion or cache repair was attempted. The warning does not change the `3 passed` result or the clean lint/format/type gate.

## Follow-up: raw mapping immutability

### RED

Added `test_check_context_freezes_raw_mapping`, which mutates the caller-owned dictionary after constructing `CheckContext` and then attempts to mutate `context.raw`.

Command run:

```powershell
uv run pytest packages/github-pr-read-model/tests/test_models.py -q
```

Result: failed as expected because the caller mutation changed `context.raw` (`expected 'queued', got 'completed'`).

### GREEN

`CheckContext.__post_init__` now makes a shallow defensive `dict` copy and wraps it in `MappingProxyType`, while the public field annotation remains `Mapping[str, object]`.

Verification commands run:

```powershell
uv run pytest packages/github-pr-read-model/tests/test_models.py -q
uv run pytest tests/test_settings.py packages/github-pr-read-model/tests/test_models.py -q
git diff --check
```

Results: passed (`2 passed`; `4 passed`; no whitespace errors). These commands use only workspace-local files and are compatible with an elevated shell if one is required by the environment.

### Follow-up concerns

The freeze is intentionally shallow: it prevents replacement or addition of top-level `raw` entries and isolates the input mapping, without changing the contract for nested mutable values.
