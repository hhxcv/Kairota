---
doc:
  updated_at: 2026-07-08
  category: interface
  status: mixed-current-planned
  audience: ai
  keywords: [api, mcp, webhook, adapter]
  description: "Defines planned external interface surfaces for Kairota."
---

# Control API

Status: mixed current and planned. Health, work item, queue summary, scheduler
cycle, claim, lease heartbeat, and stale lease reconciliation endpoints are
implemented for M1.4. Repository sync, webhooks, MCP, worker-run commands, and
adapter-backed mutations are not implemented yet.

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

## Implemented REST Surface

| Method | Path | Status |
| --- | --- | --- |
| `GET` | `/healthz` | implemented |
| `GET` | `/work-items` | implemented |
| `GET` | `/work-items/{id}` | implemented |
| `POST` | `/work-items` | implemented; requires `Idempotency-Key` |
| `GET` | `/queue/summary` | implemented |
| `POST` | `/scheduler/cycles` | implemented; requires `Idempotency-Key` |
| `POST` | `/work-items/{id}/claim` | implemented; requires `Idempotency-Key` |
| `POST` | `/leases/{id}/heartbeat` | implemented; requires `Idempotency-Key` |
| `POST` | `/reconcile/leases/expire` | implemented; requires `Idempotency-Key` |
| `POST` | `/repositories/{id}/sync` | stub; returns `not_implemented_yet` until M1.5 |

Implemented command endpoints record command idempotency in
`command_requests`. Reusing the same key and payload returns the original
result; reusing the same key with a different payload returns
`idempotency_conflict`.

## Implemented CLI Surface

| Command | Status |
| --- | --- |
| `health` | implemented |
| `db-upgrade` / `db-downgrade` | implemented |
| `work-items create/list/show/claim` | implemented |
| `queue summary` | implemented |
| `scheduler run` | implemented |
| `leases heartbeat` | implemented |
| `reconcile leases` | implemented |
| `sync repository` | stub; returns `not_implemented_yet` until M1.5 |

## Planned Adapter Set

- GitHub issues, PRs, checks, comments, labels, and merges as the first adapter.
- Future repository providers through the same core contracts.
- Codex or other AI worker runtimes.
- Local repository metadata.
- Future mail, calendar, and file-system inbox sources.
