# R1 Attention-First Triage Design

## Goal

Make the dashboard's default view answer what needs attention first while
retaining the full pull-request inventory and the existing read-only GitHub
boundary.

## Scope

Add a decision-first summary and deterministic default ordering to the existing
dashboard view. The work consumes the current normalized pull-request fields;
it does not alter GitHub collection, required-check reconciliation, filtering,
or any GitHub mutation boundary.

## Triage Summary

Place a summary above the current table with explicit counts for:

- failing checks;
- unknown required checks;
- merge-blocked pull requests;
- review-required pull requests; and
- pending checks.

Each emphasized state must include meaningful text, not color alone. A zero
count explains that no pull requests currently match that state.

## Default Ordering

All pull requests remain in the table. When no explicit filter changes the
view, sort them with this fixed priority ladder:

1. failing checks;
2. unknown required checks;
3. merge-blocked;
4. review-required;
5. pending checks; and
6. remaining non-actionable pull requests.

Fully passing CI pull requests belong in the remaining non-actionable group,
after pending checks. Within the same priority, retain the snapshot's existing
order so sorting is stable and does not invent a second policy.

## State Interpretation

The new ranking must preserve the model's distinction between all observed
checks and required checks. A pull request may therefore appear in the
unknown-required tier even when its observed checks do not fail. When multiple
attention states apply, the earliest matching tier wins.

## Testing

Add focused view tests that prove:

- the summary count for each named state;
- the complete priority ladder, including fully passing CI after pending;
- stable ordering within one tier;
- unknown-required ranking independently from all-check failure; and
- text labels for highlighted and zero-count states.

Existing dashboard tests must continue to confirm escaped repository content,
completeness warnings, refresh control, and distinct all-check/required-check
presentation.

## Out of Scope

- GitHub writes, policy decisions, and new write endpoints.
- Changing filter URL composition or responsive layout; those belong to later
  requirements.
- Treating incomplete evidence as passing.
