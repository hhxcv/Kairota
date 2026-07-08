---
doc:
  updated_at: 2026-07-08
  category: contract
  status: draft
  audience: ai
  keywords: [cost, token, duration, metrics]
  description: "Defines planned cost and duration event facts for optimization."
---

# Cost Events

Status: draft. No cost ingestion is implemented yet.

## Planned Role

Cost events help identify waste, regressions, and optimization opportunities in
AI-assisted work.

## Event Types

- Agent run duration.
- Task cycle time.
- Repository review and merge cycle time.
- CI wait and repair time.
- Review count.
- Retry count.
- Exact token and model usage when exposed by the provider.
- Estimated token usage when exact data is unavailable.

## Quality Rules

- Mark usage as `exact`, `estimated`, or `unknown`.
- Keep cost data linked to work item, agent run, repository review, and model when possible.
- Do not store transcript bodies by default.
- Use aggregated trends for routine dashboards.

## Initial Questions

- Which Codex surfaces expose per-turn or per-thread token usage.
- Whether local transcript size can be used as a bounded estimate.
- How to compare subagent cost against defect reduction or cycle-time savings.
