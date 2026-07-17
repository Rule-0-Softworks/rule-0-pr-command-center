# Rule 0 Softworks PR Command Center

A local, read-only dashboard for viewing pull-request state across the configured
Rule 0 Softworks GitHub repositories. It is intended for local operator use and
does not replace GitHub, Linear, or repository policy.

## Local setup

Use a GitHub token that you own and manage. Set it only for the current
PowerShell session; do not put its value in a committed file:

```powershell
$env:GITHUB_TOKEN = "<your human-owned GitHub token>"
# Alternatively, when your environment provides this name:
$env:GH_TOKEN = "<your human-owned GitHub token>"
```

The application reads `GITHUB_TOKEN` first and also supports `GH_TOKEN`. Do
not set both names to different values. No credential is stored by the
application, written to its output, or included in the repository.

Use a fine-grained personal access token (FGPAT) only with the repository and
pull-request read access it needs. Some check metadata can be unavailable to an
FGPAT, so the dashboard marks that check evidence as unavailable or partial
rather than making an all-clear claim. GitHub App mode supplies full fidelity
when the app has the necessary repository permissions. For clarity: classic PATs are not supported.

Install the locked environment and start the local server:

```powershell
uv sync --python 3.14
uv run serve
```

The server binds only to `127.0.0.1:8000`. Open
`http://127.0.0.1:8000` in a browser. It does not bind to a network interface.

## How the snapshot works

Startup fetches one snapshot from GitHub. Select **Refresh** to perform another
read and replace the displayed snapshot. A snapshot can be partial: when a
repository cannot be read, the dashboard continues to show the repositories it
did receive and identifies the omitted repository and its error in diagnostics.

The dashboard intentionally presents two different check classifications:

- **All returned checks** includes every check context returned for the pull
  request head SHA. This view answers what GitHub returned, including contexts
  that are not required by policy.
- **Required checks** is evaluated from the effective base-branch protection
  rules and the application identity. It can differ from all returned checks.

For either classification, `unknown` means the application refuses to claim
correctness because it could not determine the necessary information. Treat an
unknown state as a signal to inspect its diagnostics, not as passing or failing.

Rows link to a pull-request detail view. The detail view exposes the same head
SHA, returned contexts, classifications, and diagnostic codes used by the
dashboard.

## Read-only and out of scope

This application is read-only. It makes GitHub read requests only; it does not
create, update, merge, close, label, comment on, approve, or otherwise mutate
pull requests, repositories, checks, rules, or GitHub settings.

It has no database, persistence, scheduler, background polling, credential
storage, or token-management feature. It does not make policy decisions, repair
repository configuration, replace branch-protection administration, or change
Linear issue status. Use GitHub and the owning repository's established process
for every write action.

## Verification

Run the automated checks from the repository root:

```powershell
uv lock --check
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

For a credentialed local acceptance check, start the server with a
human-managed credential and inspect the dashboard and its read-only GET
endpoints:

1. Confirm the dashboard count equals the pull-request count in
   `/api/snapshot`.
2. Confirm every PR shows repository, link, author, draft state, base branch,
   SHA, review state, mergeability, merge state, both check classifications,
   and diagnostics.
3. Confirm check-state facet counts sum to the total PR count, and review and
   merge views return their expected subsets.
4. Expand a row to view contexts, then confirm its detail link shows the same
   head SHA and diagnostic codes.
5. Force a single-repository fixture failure and confirm the result shows
   partial data with the exact repository error.
6. Use browser network inspection to confirm there are no GitHub mutations and
   no credential value in requests, responses, or rendered content.
# rule-0-pr-command-center

[![CI](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/ci.yml/badge.svg)](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/codeql.yml/badge.svg)](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/codeql.yml)
[![Codecov](https://codecov.io/gh/Rule-0-Softworks/rule-0-pr-command-center/graph/badge.svg)](https://codecov.io/gh/Rule-0-Softworks/rule-0-pr-command-center)
[![Release Please](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/release-please.yml/badge.svg)](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/actions/workflows/release-please.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)

PR visbility and command center, the way you want it, every time
