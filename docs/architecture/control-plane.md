---
doc:
  updated_at: 2026-07-10
  category: architecture
  status: current
  audience: ai
  keywords: [control-plane, architecture, product-scope]
  description: "Defines Kairota's current local Issue scheduling boundary."
---

# Control Plane Architecture

## Purpose

Kairota provides mechanical project scheduling for one or more GitHub projects.
It runs locally, synchronizes Issues, stores dependency analysis supplied by the
managed project's main AI, computes readiness, and exposes progress to humans.

## Ownership

| Owner | Facts and actions |
| --- | --- |
| GitHub | Project identity, Issue number/title/URL, open or closed state |
| Managed project's main AI | Issue interpretation, dependency graph, manual holds, worker cap, subagent lifecycle, validation, GitHub close |
| Kairota | Registered projects, sync health, dependency edges, five scheduling states, atomic claim/release, UI read model |
| Subagent | Assigned project work and reporting back to its main AI; never Kairota calls |
| Human | Starts Kairota, registers projects, observes progress, resolves product decisions |

## Runtime Shape

```text
GitHub REST Issues ----> sync reducer ----> managed_issues
       ^                    |                    |
       |                    +--> sync health    +--> five-state derivation
Issue webhook                                   |
       |                                        v
       +---- exact REST refresh         REST API and human UI
                                                ^
                                                |
                                    managed-project main AI
```

- Polling is the convergence and repair path.
- A signed Issue webhook never becomes scheduler truth directly; it triggers an
  exact REST Issue refresh.
- Synchronization for the same project is serialized inside the local service.
- Failed or stale synchronization makes claims unavailable.
- SQLite is internal to Kairota and upgraded automatically. Versioned atomic
  updates protect the only contested boundary, `ready -> in_progress`.

## Current Data

The active schema contains `projects`, `project_sync_states`, `managed_issues`,
`issue_dependencies`, `command_requests`, `inbound_events`, and `audit_events`.
The M1 prototype tables were intentionally destroyed; no migration or backup is
part of this milestone.

## Product Boundary

Kairota does not contain worker, execution, attempt, resume, requeue, heartbeat,
lease, lock, PR, CI, or review scheduling models. These would duplicate the
single main AI or add facts that do not decide Issue readiness.

Future project-management information may be synchronized for display, but it
must remain outside the readiness predicate unless a new accepted design proves
otherwise.
