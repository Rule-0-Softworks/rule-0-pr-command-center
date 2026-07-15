# PR Command Center Milestones Design

## Purpose

Define two evidence-based delivery gates for the R0S PR Command Center project.
The gates measure real operational readiness rather than abstract progress.
Both preserve the product's read-only GitHub boundary.

## Milestone Sequence

1. **M0 — Dev Testing Viable** establishes that a maintainer can use live
   GitHub data for trustworthy development testing.
2. **M1 — Enhanced MVP Candidate** establishes that the planned decision-first
   experience is complete and has passed a live maintainer scenario trial.

M1 follows M0. Neither gate includes Engineering OS orchestration, durable
execution-session storage, or GitHub write actions. A future Engineering OS
integration may consume the dashboard as a read-only PR-state surface.

## M0 — Dev Testing Viable

### Entry condition

The dashboard has a maintainer-configured GitHub token and can load the
intended repositories with live data.

### Exit criteria

- One maintainer completes a real triage session using live GitHub data; test
  fixtures alone cannot satisfy the gate.
- The maintainer can distinguish observed checks from required checks, identify
  at least one actionable pull request, and navigate to its GitHub source.
- The dashboard does not imply write access.
- Snapshot freshness, partial-data warnings, and token or access errors are
  sufficiently clear that the dashboard cannot present a false all-clear.
- The maintainer records a short test note with the repositories, time window,
  live scenarios observed, and defects found.
- No unresolved defect may make triage misleading or prevent the live trial.

### Gate decision

The maintainer explicitly declares the dashboard viable for continued
development testing. Defects may remain when they do not violate the exit
criteria.

## M1 — Enhanced MVP Candidate

### Entry condition

M0 has passed and the feature's requirements are ready for acceptance.

### Exit criteria

- Requirements R1 through R5 are implemented, tested, and accepted:
  attention-first triage, responsive hierarchy, decision-ready detail,
  composable/shareable filters, and explicit snapshot freshness/completeness.
- One maintainer completes an end-to-end live GitHub trial and confirms every
  requested capability is available and working.
- The evidence covers these scenarios:
  - an all-green CI view;
  - a pull request with a failing GitHub Actions check;
  - pending or unknown-required-check treatment;
  - review-required or merge-blocked treatment when live data exists;
  - composed filters that survive a shareable URL;
  - narrow-screen navigation and pull-request detail; and
  - a stale, partial, or error state that preserves the last good snapshot.
- A live scenario that cannot be produced is documented with its cause and a
  named substitute verification method; it cannot silently pass.
- Evidence includes requirement acceptance links, automated-test results, and
  a maintainer scenario checklist with live pull-request URLs and timestamps.

### Gate decision

The project is an Enhanced MVP Candidate: credible for broader MVP
consideration, still read-only, and not yet committed to Engineering OS
integration.

## Relationships and Dependencies

M0 is the prerequisite for M1. Within M1, R1 enables the remaining experience
work; R2 enables R4. The final gate requires both requirement acceptance and
the live scenario evidence, preventing either implementation completeness or
operator usability from being treated as sufficient on its own.
