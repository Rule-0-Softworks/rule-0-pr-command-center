# Rule 0 Softworks PR Project Synchronization

The custom PR Command Center has been retired in favor of native GitHub Projects.
This default branch intentionally contains only the active GitHub Actions workflow
that synchronizes open pull requests into GitHub Project 5.

## Active automation

`.github/workflows/sync-open-prs.yml` runs every 12 hours at minute 30 and can also be
started manually with **Run workflow**. It requires the repository secret
`R0S_PROJECT_TOKEN`; secret values are never stored in this repository.

## Legacy implementation

The complete read-only dashboard, its tests, documentation, and historical
automation are preserved for reference on
[`chore/legacy-pr-command-center`](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/tree/chore/legacy-pr-command-center).
The protected final checkpoint is the
[`legacy-pr-command-center-final`](https://github.com/Rule-0-Softworks/rule-0-pr-command-center/tree/legacy-pr-command-center-final)
annotated tag.
