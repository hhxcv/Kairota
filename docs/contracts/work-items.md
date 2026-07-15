---
doc:
  updated_at: 2026-07-10
  category: contract
  status: current
  audience: ai
  keywords: [managed-issue, dependency, state]
  description: "Defines synced GitHub Issue and dependency facts."
---

# Managed Issues

A managed Issue is Kairota's durable scheduling projection of one GitHub Issue.
Kairota does not create independent work items.

| Field | Source | Required | Purpose |
| --- | --- | --- | --- |
| Project, provider Issue ID, number | GitHub sync | yes | Stable identity and project isolation |
| Title, URL | GitHub sync | yes | Human and main-AI context |
| Source state | GitHub sync | yes | `closed` satisfies dependencies |
| Source update and sync times | GitHub sync | optional | Freshness and diagnosis |
| Dependency edges | Main AI analysis | required before ready | Readiness computation |
| Manual hold reason | Main AI analysis | optional | Explicit non-dependency block |
| Analysis version | Kairota | yes | Prevent stale graph replacement |
| Scheduling state/version | Kairota | yes | UI state and atomic claim |
| In-progress since | Kairota claim | optional | Human visibility and restart reconciliation |

Analysis completeness is explicit. An empty dependency set is valid only after
the main AI submits analysis; a newly synchronized Issue is not assumed ready.

Closing a GitHub Issue sets `closed`. Reopening it clears the old analysis,
because the reopened scope may differ. Releasing active work has the same
invalidation behavior.
