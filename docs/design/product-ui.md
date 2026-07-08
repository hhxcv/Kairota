---
doc:
  updated_at: 2026-07-08
  category: design
  status: draft
  audience: ai
  keywords: [ui, dashboard, workbench, product-design]
  description: "Defines the planned Kairota UI surfaces and design priorities."
---

# Product UI

Status: draft. No UI is implemented yet.

## First Screen

The first implemented UI should be an operational queue surface, not a marketing
landing page.

Primary regions:

- Ready work.
- Running workers.
- Blocked work.
- Waiting repository checks or review.
- Human or delegated AI decision inbox.
- Recent events and failures.

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
