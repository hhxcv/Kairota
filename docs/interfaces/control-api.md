---
doc:
  updated_at: 2026-07-08
  category: interface
  status: draft
  audience: ai
  keywords: [api, mcp, webhook, adapter]
  description: "Defines planned external interface surfaces for Kairota."
---

# Control API

Status: draft. No API is implemented yet.

## Planned Interfaces

| Interface | Purpose |
| --- | --- |
| Web UI | Human queue, decision, cost, and project overview |
| CLI | Local administration and scripted checks |
| REST API | Stable integration surface for tools and adapters |
| MCP Server | AI agent access to bounded Kairota actions |
| Webhook Receiver | Repository, CI, and future external event ingestion |

## API Principles

- Expose bounded actions, not raw database mutation.
- Require idempotency keys for public or repeated mutations.
- Return machine-readable reasons for blocked scheduling.
- Separate read models from mutation commands.
- Keep adapter-specific payloads out of core contracts.

## Planned Adapter Set

- GitHub issues, PRs, checks, comments, labels, and merges as the first adapter.
- Future repository providers through the same core contracts.
- Codex or other AI worker runtimes.
- Local repository metadata.
- Future mail, calendar, and file-system inbox sources.
