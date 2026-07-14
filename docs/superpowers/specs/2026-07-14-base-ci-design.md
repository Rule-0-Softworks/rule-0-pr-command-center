# Base CI Design

## Goal

Establish repository-owned GitHub automation for validation, security scanning,
dependency updates, release PR creation, coverage reporting, and discoverable
status badges.

## Scope

- Add a CI workflow for pull requests targeting `dev` or `main`, plus pushes to
  those branches.
- Add a separate CodeQL workflow for Python, including a monthly scheduled scan
  on the first day of the month.
- Add weekly Dependabot updates for GitHub Actions and Python dependencies.
- Add Release Please to create or update release pull requests from Conventional
  Commits; it will not publish releases automatically.
- Generate and upload a Pytest coverage XML report to Codecov using the
  organization-level `CODECOV_TOKEN` secret.
- Add README badges for CI, CodeQL, Codecov, Release Please, the supported
  Python version, and the project license.
- Add local configuration-contract tests so the automation configuration is
  checked by the existing test suite.

## Workflow Design

`ci.yml` will run on Ubuntu for pushes to `dev` and `main`, and pull requests
targeting either branch. It will install the locked Python 3.12 environment
through UV, validate `uv.lock`, run Ruff linting and formatting checks, run Ty,
then run Pytest with `pytest-cov` to produce `coverage.xml`. Codecov uploads
that file using
`${{ secrets.CODECOV_TOKEN }}` and fails the job when the upload cannot be
completed.

`codeql.yml` will use GitHub's advanced setup for Python on pushes and pull
requests targeting `main`, plus a UTC monthly scheduled run at `06:00` on the
first day of the month (`0 6 1 * *`). It will grant only the permissions
required to read repository contents and upload security events.

`release-please.yml` will run only on pushes to `main`, with pull-request and
contents write permissions, to maintain a release PR based on the repository's
existing Conventional Commit history.

## Action Supply-Chain Policy

Every third-party action reference will be pinned to a full commit SHA. The
following current major-version SHAs were resolved on 2026-07-14 and will have
their major version recorded in an adjacent comment:

- `actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10` (`v6`)
- `actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1` (`v6`)
- `astral-sh/setup-uv@94527f2e458b27549849d47d273a16bec83a01e9` (`v7`)
- `codecov/codecov-action@04b047e8bb82a0c002c8312c1c880fbc6a999d45` (`v5`)
- `github/codeql-action@1ad29ea4a422cce9a242a9fae469541dcd08addc` (`v4`)
- `googleapis/release-please-action@8b8fd2cc23b2e18957157a9d923d75aa0c6f6ad5` (`v4`)

Dependabot will check GitHub Actions and Python/UV dependencies weekly. Its
GitHub Actions configuration will group `github/codeql-action/*` updates into a
single `codeql-actions` pull request, preventing `init` and `analyze` from
moving independently. Pull requests must preserve full-SHA pinning.

## Testing and Failure Handling

Configuration-contract tests will parse the YAML files and assert the required
triggers, commands, SHA-pinned actions, Codecov token wiring, and Dependabot
ecosystems. These tests will fail before the workflows exist, then pass after
the minimal configuration is added. Local verification will run the current
README commands and the configuration-contract tests. GitHub-hosted workflow
execution and Codecov upload require the subsequent pull request on GitHub.

## Bootstrap Behavior

The current main branch has no Python project. The CI and CodeQL workflows will
first check out the repository and emit a project-present output. Their quality
and analysis jobs will depend on that output and run only when the required
project files exist. This permits the CI-only branch to merge first without a
failing run; after main is merged into the application feature branch, the full
checks and Codecov upload run on that branch's pull request.

Local application commands cannot run from this bootstrap branch. Verification
will inspect the exact YAML files, validate the pinned action SHAs, and run
git diff --check.

## Non-Goals

- No automatic package publication, deployment, release artifact generation,
  or GitHub release creation.
- No branch-protection changes or GitHub organization setting changes.
- No application dependency changes; CI installs `pytest-cov` transiently
  through UV to create the requested coverage report while leaving the future
  project lockfile unchanged.
