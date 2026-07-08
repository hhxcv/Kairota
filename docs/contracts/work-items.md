---
doc:
  updated_at: 2026-07-08
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

| Field | Purpose |
| --- | --- |
| Title | Human-readable task name |
| Status | Queue state for scheduler and UI |
| Priority | Stable ordering when multiple items are ready |
| Risk | Review and gate intensity |
| Work Type | Implementation, docs, test, design, governance, or operations |
| Dependencies | Work items that must finish before this item can run |
| Expected Touch | Planned code, docs, contract, or integration areas |
| Conflict Keys | Logical locks that prevent unsafe parallel writes |
| Acceptance | Done criteria |
| Validation | Required checks or evidence |
| Autonomy Mode | Whether AI may continue without human presence |
| Repository Id | Optional Kairota repository scope for managed-project scheduling |
| Source Link | External issue, ticket, or request that originated the item |

## Implemented Commands

| Surface | Purpose |
| --- | --- |
| `POST /work-items` | Create a Kairota work item with optional repository scope. |
| `GET /work-items` | List work items, optionally filtered by status or repository id. |
| `GET /work-items/{id}` | Read one work item. |
| `POST /work-items/{id}/triage` | Let project AI or a human set scheduling facts after issue analysis. |
| `kairota work-items create/list/show/triage/claim` | Local CLI access to the same core service layer. |

Triage is explicit. Kairota does not infer dependency edges, expected touch,
validation, conflict keys, or readiness from issue prose by itself.

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
- Managed project AI analyzes the issue and submits dependency, conflict,
  acceptance, validation, and readiness facts back to Kairota.
