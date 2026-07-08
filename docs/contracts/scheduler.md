---
doc:
  updated_at: 2026-07-08
  category: contract
  status: mixed-current-planned
  audience: ai
  keywords: [scheduler, lease, claim, conflict-lock]
  description: "Defines planned scheduler contracts for deterministic AI work assignment."
---

# Scheduler

Status: mixed current and planned. Deterministic scheduler planning,
repository-scoped candidate loading, claim-next, leases, lease heartbeats,
stale lease expiry, conflict locks, scheduler decision records, and blocked
reason codes are implemented. MCP exposure and broader capacity policy remain
planned.

## Planned Responsibilities

- Select ready work items for the whole queue or a registered repository.
- Enforce dependencies.
- Enforce conflict locks.
- Enforce worker capacity.
- Claim work with a lease and fencing token.
- Record why work was assigned or rejected.
- Reconcile repository review, check, worker, and merge events through service
  commands and sync reducers.

## Implemented Surfaces

| Surface | Purpose |
| --- | --- |
| `POST /scheduler/cycles` | Records deterministic planning decisions for a queue or repository scope. |
| `GET /queue/ready` | Lists ready work, optionally by repository id. |
| `POST /queue/claim-next` | Plans and claims the next schedulable work item in one idempotent command. |
| `GET /queue/summary` | Reads status, active lease, and active lock counts. |
| `GET /queue/workbench` | Reads the human queue view, optionally by repository id. |
| `POST /leases/{id}/heartbeat` | Refreshes valid lease authority. |
| `POST /reconcile/leases/expire` | Expires stale leases and releases their locks. |

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

Repository scoping filters candidate work items by `repository_id`, but active
conflict locks remain global so two projects cannot accidentally mutate a shared
Kairota runtime surface in parallel.

## Non-Goals

- AI semantic triage inside the deterministic scheduler.
- Direct code editing.
- Direct merging that bypasses repository gates.
- Deciding issue dependency relationships without managed-project AI input.
