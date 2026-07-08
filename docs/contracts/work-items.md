---
doc:
  updated_at: 2026-07-08
  category: contract
  status: draft
  audience: ai
  keywords: [work-item, task, dependency, status]
  description: "Defines planned work item facts for scheduler and UI use."
---

# Work Items

Status: draft. No schema is implemented yet.

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
| Source Link | External issue, ticket, or request that originated the item |

## Status Model

Initial planned states:

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
