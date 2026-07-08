---
doc:
  updated_at: 2026-07-08
  category: design
  status: mixed-current-planned
  audience: ai
  keywords: [ui, dashboard, workbench, product-design]
  description: "Defines Kairota UI surfaces and design priorities."
---

# Product UI

Status: mixed current and planned. The M1 queue workbench with recovery signals
is implemented. Cost, project management, and cross-project experience surfaces
are planned.

## Implemented First Screen

The first UI is an operational queue surface, not a marketing landing page.
It renders Kairota API read models. If API data is unavailable, it shows an
explicit empty or unavailable state; it must not fall back to fake queue data in
product runtime.

Primary regions:

- Ready work.
- Running workers.
- Blocked work.
- Waiting repository checks or review.
- Human or delegated AI decision inbox.
- Recovery signals.
- Recent events and failures.
- Selected work item detail with scheduling facts, worker-run state, and
  repository gate summary when present.

## Design Principles

- Prefer dense, calm, operational UI over decorative presentation.
- Show state transitions, blockers, and next action directly.
- Make stale state and missing scheduling facts visible.
- Keep cost and duration signals near the work they explain.
- Use project style consistently once visual tokens exist.

## Future Surfaces

- Cost trends and waste analysis.
- Project timeline and retrospective view.
- Agent utilization and quality view.
- Cross-project experience registry.
- Command center for common actions.
