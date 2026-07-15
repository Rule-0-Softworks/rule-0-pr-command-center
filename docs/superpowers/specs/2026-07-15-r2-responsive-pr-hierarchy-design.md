# R2 Responsive PR Information Hierarchy Design

## Goal

Keep the PR inventory usable on narrow screens without weakening the dense,
scannable desktop experience or the application's read-only GitHub boundary.

## Responsive Representations

Render two server-side representations from the same ordered PR sequence:

- A desktop table retains the existing dense inventory and its current fields.
- A narrow-screen card list replaces horizontal table scanning below the
  responsive breakpoint.

CSS, not JavaScript, selects the visible representation. No client-side
framework or design-system dependency is introduced.

## Narrow-Screen Card Contract

Every card exposes these fields without horizontal scanning:

- repository;
- pull request number and title;
- attention state;
- required-check state;
- review state; and
- a detail link.

Attention state uses the existing triage-tier meaning, not a new independent
classification. Required-check state continues to be shown separately from all
observed checks.

## Progressive Disclosure

Each card uses a native `<details>` element for secondary metadata:

- author;
- draft status and base branch;
- head SHA;
- mergeability and merge state; and
- diagnostics.

The desktop table remains the place for the full at-a-glance inventory. The
card disclosure does not hide any field required by the narrow-screen card
contract.

## Accessibility

Use semantic list/card markup, ordinary links for detail navigation, and the
native keyboard behavior of `<details>/<summary>`. Preserve the existing
visible focus indicators for links and summary controls. Do not encode state
meaning in color alone.

## Testing

Add rendering/view tests that prove:

- the desktop table and narrow card list are both rendered from the same PR;
- each card contains every required visible field and its detail URL;
- secondary metadata appears only in the card disclosure; and
- the stylesheet has a narrow-screen breakpoint that hides the desktop table,
  shows the card list, and does not require horizontal table scanning.

## Out of Scope

- Changing triage priority, snapshot freshness, filters, collection, or GitHub
  access.
- Adding JavaScript, a client-side framework, or a design-system dependency.
