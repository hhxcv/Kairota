---
doc:
  updated_at: 2026-07-10
  category: design
  status: current
  audience: ai
  keywords: [ui, dashboard, issues, progress]
  description: "Defines the current unified managed Issue dashboard."
---

# Product UI

The first screen is a dense operational Issue dashboard, not a landing page.
It renders only API data and must never substitute fixtures when the API is empty
or unavailable.

## Required Regions

- Header: Kairota identity, service health, refresh, and add-project command.
- Project filter: searchable multi-select, all-projects mode, selected count,
  clear action, and per-project sync health.
- State summary: the five scheduling states as both scoped counts and filters.
- Issue list: project, Issue, state, dependency progress or blocker, and last
  synchronization time, with search and pagination.
- Detail drawer: GitHub link, dependency list, hold/block reasons, current state,
  and useful timing facts.
- Explicit loading, empty, disconnected, sync-error, and mutation-error states.

## Interaction Rules

- Counts use the selected-project and search scope, not fixture totals.
- Project and state selections are represented in API query parameters.
- Clicking a row preserves the list context and opens a side drawer.
- Add-project and manual-sync commands use unique idempotency keys and refresh
  project and Issue reads after success.
- The UI is human observation and project setup; dependency analysis and claims
  remain main-AI API actions.

## Visual Rules

Use a quiet work-tool palette with semantic state colors, compact typography,
stable table geometry, Lucide icons, and at most 8px radius. Avoid hero content,
decorative gradients, nested cards, fake charts, or explanatory marketing copy.
Desktop and mobile layouts must preserve labels, controls, and state without
overlap or horizontal loss of primary Issue identity.
