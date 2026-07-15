---
doc:
  updated_at: 2026-07-10
  category: contract
  status: current
  audience: ai
  keywords: [scheduler, dependency, claim, release]
  description: "Defines minimal readiness and claim behavior."
---

# Scheduler Contract

## Readiness Predicate

An Issue is claimable exactly when:

- its scheduling state is `ready`;
- its project is enabled;
- the last GitHub synchronization succeeded and is recent;
- the claim supplies the current scheduling version.

`ready` itself means analysis is complete, no manual hold exists, and every
dependency Issue is closed.

## Concurrency Boundary

The claim uses a conditional database update on Issue ID, state, and scheduling
version. One winner moves the row to `in_progress`; stale or competing commands
receive a conflict and must re-read.

Kairota has no worker cap or worker identity. The unique project main AI tracks
its own subagents, chooses no more work than its local capacity, and claims each
selected Issue immediately before assignment.

## Recovery

The main AI reconciles all `in_progress` Issues before new dispatch. Release is
the conservative recovery command when active ownership cannot be proved. It
returns the Issue to `needs_analysis`, preventing silent reuse of potentially
stale assumptions.

## Excluded Inputs

Priority, risk, expected files, acceptance text, validation, PR, review, CI,
worker progress, cost, and retries are not scheduler facts. They may exist in the
managed project or future human views without changing eligibility.
