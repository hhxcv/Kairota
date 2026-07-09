---
doc:
  updated_at: 2026-07-09
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
reason codes are implemented. `claim-next` enforces an optional
`max_active_leases` worker cap for repository-scoped or global claims and
returns aggregate blocked reason counts when no candidate can be claimed. MCP
exposure remains planned.

## Implemented Responsibilities

- Select ready work items for the whole queue or a registered repository.
- Enforce dependencies, where a dependency is satisfied by a `done` work item.
- Enforce conflict locks.
- Enforce worker capacity.
- Claim work with a lease and fencing token.
- Record why work was assigned or rejected.

The scheduler does not require expected touch, acceptance, validation, CI,
review, or PR gate fields to assign work. Those facts are project-management
and workbench facts.

## Implemented Surfaces

| Surface | Purpose |
| --- | --- |
| `POST /scheduler/cycles` | Records deterministic planning decisions for a queue or repository scope. |
| `GET /queue/ready` | Lists ready work, optionally by repository id. |
| `POST /queue/claim-next` | Plans and claims the next schedulable work item in one idempotent command. Supports optional `max_active_leases`. |
| `GET /queue/summary` | Reads status, active lease, and active lock counts. |
| `GET /queue/workbench` | Reads the human queue view, optionally by repository id; ready-status work with unmet dependencies or active conflicts is shown with blocker-specific actions. |
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

## Worker Capacity

`POST /queue/claim-next` accepts `max_active_leases`. When the current active
lease count for the requested `repository_id` is greater than or equal to that
cap, Kairota records a `capacity_blocked` scheduler cycle and returns
`blocked_by_capacity` instead of issuing another lease.

The cap is supplied by the managed project's AI loop because Kairota does not
own project staffing policy. The same cap must be sent on every claim attempt in
that loop. Direct `POST /work-items/{id}/claim` remains a lower-level command and
does not apply this project-loop capacity policy.

## Scheduling Inputs

Current scheduler eligibility uses only:

- `status == ready`;
- dependency work items are `done`;
- remaining worker capacity;
- conflict keys and active conflict locks.

Priority, risk, and creation order affect deterministic ordering. Expected
touch, acceptance, validation, CI status, review status, and PR state are kept
for triage, reporting, and UI context; they are not hard scheduling gates.

`status=ready` is intent, not proof that work is claimable now. The planner and
workbench still check dependencies and active conflict locks before presenting
work as claimable.

## Conflict Locks

Conflict keys prevent unsafe parallel work.

Planned lock sources:

- Active claimed work.
- Explicit work item conflict keys.
- Conservative fallback for missing conflict keys.

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
