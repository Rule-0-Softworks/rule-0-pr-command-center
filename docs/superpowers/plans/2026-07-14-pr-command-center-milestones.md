# PR Command Center Milestones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two evidence-based milestones—M0 — Dev Testing Viable and M1 — Enhanced MVP Candidate—to the R0S PR Command Center Linear project.

**Architecture:** This is a Linear-only planning change. Both milestones belong to the existing R0S PR Command Center project, inherit its read-only GitHub product boundary, and use explicit exit criteria as their definition of done. M1 depends on M0 and adds both requirement completion and live operator-scenario evidence.

**Tech Stack:** Linear project and milestone records; GitHub-backed operator trial evidence.

## Global Constraints

- Use the existing `R0S PR Command Center` project; do not create a duplicate project.
- The available Linear milestone connector has no milestone-status field; do not
  change project or issue statuses while creating these records.
- Do not record passing or completion evidence on either milestone until its
  evidence gate is actually met.
- Do not move any Linear issue to In Review or Done manually.
- M0 and M1 require live GitHub data; fixtures alone cannot satisfy either live-trial criterion.
- The product remains read-only: no Engineering OS orchestration, durable execution-session storage, or GitHub write actions are in scope.
- Any future Engineering OS connection is limited to a potential read-only PR-state surface.

---

### Task 1: Confirm the project target and current hierarchy

**Files:**
- Read: `docs/superpowers/specs/2026-07-14-pr-command-center-milestones-design.md`
- Read: Linear project `R0S PR Command Center`

**Interfaces:**
- Consumes: Linear project name `R0S PR Command Center`.
- Produces: verified project ID used by Tasks 2 and 3.

- [ ] **Step 1: Read the approved milestone design**

Run: open `docs/superpowers/specs/2026-07-14-pr-command-center-milestones-design.md`.

Expected: the document specifies M0 Dev Testing Viable, M1 Enhanced MVP Candidate, live GitHub evidence, and the read-only boundary.

- [ ] **Step 2: Retrieve the Linear project by exact name**

Use the Linear project search and then retrieve the matching project record.

Expected: exactly one project named `R0S PR Command Center`, attached to the `R0S Engineering Operating System` initiative.

- [ ] **Step 3: Verify the current feature chain remains intact**

Retrieve feature `RUL-2126` and its requirements R1–R5.

Expected: RUL-2126 remains under RUL-2125 and RUL-2127 through RUL-2131 remain its children; do not alter their statuses or dependencies.

- [ ] **Step 4: List existing project milestones before writing**

Use the Linear milestone-list action for the verified project. If a milestone
named `M0 — Dev Testing Viable` or `M1 — Enhanced MVP Candidate` already exists, retrieve
it by ID. Reuse it only when its project and description already match this
plan; otherwise stop and ask the project owner before changing an existing
milestone.

Expected: the executor has a recorded no-duplicate decision for each milestone.

### Task 2: Create M0 — Dev Testing Viable

**Files:**
- Read: `docs/superpowers/specs/2026-07-14-pr-command-center-milestones-design.md`
- Modify: Linear project `R0S PR Command Center`

**Interfaces:**
- Consumes: verified R0S PR Command Center project ID from Task 1.
- Produces: milestone `M0 — Dev Testing Viable` with no passing evidence recorded.

- [ ] **Step 1: Create the M0 milestone in the verified project**

Use the Linear milestone-create action with this name and description:

```text
M0 — Dev Testing Viable

Gate: one maintainer completes a real triage session using live GitHub data for
the intended repositories. The maintainer can distinguish observed from
required checks, identify an actionable PR, and navigate to GitHub without the
dashboard implying write access. Freshness, partial-data, token, and access
states must not create a false all-clear.

Evidence: a maintainer test note with tested repositories, time window, live
scenarios observed, and defects found. No unresolved defect may make triage
misleading or prevent the trial.
```

Expected: M0 is attached only to the existing project. No project or issue
status has changed, and no passing evidence is recorded.

- [ ] **Step 2: Retrieve M0 and verify its gate text**

Use the Linear milestone retrieval action.

Expected: name, description, and project assignment match Step 1 exactly. The
milestone has no passing evidence, and no project or issue status has changed.

### Task 3: Create M1 — Enhanced MVP Candidate

**Files:**
- Read: `docs/superpowers/specs/2026-07-14-pr-command-center-milestones-design.md`
- Modify: Linear project `R0S PR Command Center`

**Interfaces:**
- Consumes: verified project ID from Task 1 and M0 from Task 2.
- Produces: milestone `M1 — Enhanced MVP Candidate` with no passing evidence
  recorded and with M0 named as its prerequisite.

- [ ] **Step 1: Create the M1 milestone in the verified project**

Use the Linear milestone-create action with this name and description:

```text
M1 — Enhanced MVP Candidate

Gate: M0 has passed; requirements R1–R5 are implemented, tested, and accepted;
and one maintainer confirms every requested capability is available and working
in an end-to-end trial using live GitHub data.

Evidence must cover all-green CI, failing GitHub Actions CI, pending or
unknown-required checks, review-required or merge-blocked treatment when live
data exists, composed shareable filters, narrow-screen navigation and PR
detail, and preservation of the last good snapshot during stale, partial, or
error states. A scenario unavailable in live data must name its cause and a
substitute verification method. Record requirement links, automated-test
results, and a scenario checklist with live PR URLs and timestamps.

Boundary: this remains read-only and does not commit the project to Engineering
OS integration.
```

Expected: M1 is attached only to the existing project. No project or issue
status has changed, and no passing evidence is recorded.

- [ ] **Step 2: Record M0 as M1's predecessor**

The available Linear milestone connector does not expose predecessor relations.
Place the explicit `M0 must pass first` dependency at the top of M1's
description, preserving it if M1 is reused from Task 1 Step 4.

Expected: a project viewer can determine that M0 must pass before M1 is eligible to pass.

- [ ] **Step 3: Retrieve M1 and verify its gate text**

Use the Linear milestone retrieval action.

Expected: name, live-scenario checklist, explicit M0 prerequisite, read-only
boundary, and project assignment match Steps 1 and 2. The milestone has no
passing evidence, and no project or issue status has changed.

### Task 4: Verify the project-level milestone ladder

**Files:**
- Read: Linear project `R0S PR Command Center`

**Interfaces:**
- Consumes: M0 from Task 2 and M1 from Task 3.
- Produces: verified project milestone ladder ready for execution tracking.

- [ ] **Step 1: Retrieve the project with milestones included**

Use the Linear project retrieval action.

Expected: the project shows both M0 — Dev Testing Viable and M1 — Enhanced MVP Candidate
exactly once.

- [ ] **Step 2: Review scope and status safety**

Confirm that no existing project, initiative, Epic, Feature, requirement, or GitHub sync attachment was changed as a side effect.

Expected: only two new milestones exist; all existing issues retain their prior statuses and relationships.

- [ ] **Step 3: Report the completed gate definitions**

Recheck RUL-2127's current status and dependencies. Provide the milestone URLs,
the M0 → M1 order, and RUL-2127 as the next eligible work item only if its
current Linear state still supports that claim.

Expected: the handoff states that passing a milestone requires the specified live evidence, not merely completion of tickets.

## Self-Review

- Spec coverage: Task 2 covers every M0 entry, evidence, and exit condition. Task 3 covers M1's R1–R5 completion, live scenario pack, substitute-verification rule, and read-only boundary. Task 4 verifies no unrelated Linear state changes.
- Placeholder scan: no unresolved placeholders or generic implementation instructions remain.
- Consistency: M0 precedes M1 in the plan and in M1's gate text; both use the same existing project and retain the same read-only boundary. The plan never assumes an unsupported milestone-status field.
