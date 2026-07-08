---
doc:
  updated_at: 2026-07-08
  category: contract
  status: draft
  audience: ai
  keywords: [scheduler, lease, claim, conflict-lock]
  description: "Defines planned scheduler contracts for deterministic AI work assignment."
---

# Scheduler

Status: draft. No scheduler is implemented yet.

## Planned Responsibilities

- Select ready work items.
- Enforce dependencies.
- Enforce conflict locks.
- Enforce worker capacity.
- Claim work with a lease.
- Record why work was assigned or rejected.
- Reconcile repository review, check, worker, and merge events.

## Determinism

Repeated scheduling with the same inputs should produce the same plan.

Stable ordering:

1. priority;
2. risk;
3. creation order or numeric id.

## Lease Rules

- A worker must hold a valid lease before public mutation.
- Lease owner is a logical slot or worker identity, not a private runtime id.
- Workers must re-read lease before branch creation, PR creation, gate actions,
  and final state updates.
- Expired leases are recoverable by scheduler reconciliation.

## Conflict Locks

Conflict keys prevent unsafe parallel work.

Planned lock sources:

- Active claimed work.
- Open or merge-armed PRs.
- Explicit work item conflict keys.
- Conservative fallback for missing or ambiguous touch data.

Default serial areas:

- scheduler kernel;
- agent governance;
- repository automation;
- shared contracts;
- security or privacy boundaries.

## Non-Goals

- AI semantic triage inside the deterministic scheduler.
- Direct code editing.
- Direct merging that bypasses repository gates.
