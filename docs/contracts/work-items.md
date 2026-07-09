---
doc:
  updated_at: 2026-07-09
  category: contract
  status: mixed-current-planned
  audience: ai
  keywords: [work-item, task, dependency, status]
  description: "Defines work item facts for scheduler and UI use."
---

# Work Items

Status: mixed current and planned. M1 work item schema, API/CLI create/read,
repository scoping, dependency facts, conflict keys, and triage updates are
implemented. Semantic issue analysis remains the managed project's AI
responsibility.

## Planned Role

A work item is the durable unit of schedulable work. It may mirror a GitHub
issue in the first adapter, but Kairota owns the scheduling facts.

## Core Facts

| Field | Role |
| --- | --- |
| Status | Scheduler and UI queue state. `ready` is eligible; `done` satisfies dependencies. |
| Dependencies | Scheduler-critical predecessor work items. |
| Conflict Keys | Scheduler-critical logical locks for unsafe parallel writes. |
| Priority | Scheduler ordering when multiple items are eligible. |
| Risk | Ordering and reporting signal, not an eligibility gate. |
| Repository Id | Optional scheduler scope for managed-project queues. |
| Title | Human-readable task name. |
| Work Type | Reporting and filtering dimension. |
| Expected Touch | Management and workbench context. |
| Acceptance | Management and completion-context field. |
| Validation | Management and evidence field. |
| Autonomy Mode | Management and policy context. |
| Source Link | External issue, ticket, or request that originated the item. |

## Implemented Commands

| Surface | Purpose |
| --- | --- |
| `POST /work-items` | Create a Kairota work item with optional repository scope. |
| `GET /work-items` | List work items, optionally filtered by status or repository id. |
| `GET /work-items/{id}` | Read one work item. |
| `POST /work-items/{id}/triage` | Let project AI or a human set scheduling facts after issue analysis. |
| `kairota work-items create/list/show/triage/claim` | Local CLI access to the same core service layer. |

Triage is explicit. Kairota does not infer dependency edges, conflict keys, or
readiness from issue prose by itself. Expected touch, acceptance, validation,
risk, work type, and autonomy mode improve reporting and workbench quality, but
they are not required for scheduler eligibility.

## Status Model

Implemented states:

`Backlog -> Ready -> Claimed -> Implementing -> PR Open -> Waiting Checks ->
Merge Armed -> Merged -> Done`

Blocking states:

- `Needs Triage`
- `Blocked`
- `Human Decision`
- `Strict AI Review`
- `CI Failed`
- `Gate Failed`

## Truth Rules

- Kairota work item records own scheduling truth.
- External issues may provide requirements and discussion.
- Repository PRs own code review, checks, and merge state.
- UI fields may cache external status but must be reconcilable.
- GitHub sync creates newly discovered issues in `Needs Triage`.
- GitHub issue close is the current completion signal for synced issue work and
  moves the work item to `Done`.
- Managed project AI analyzes the issue and submits dependency, conflict, and
  readiness facts back to Kairota. Other fields are project-management context.
