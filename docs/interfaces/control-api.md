---
doc:
  updated_at: 2026-07-10
  category: interface
  status: current
  audience: ai
  keywords: [api, rest, webhook, github]
  description: "Defines the implemented local REST and GitHub webhook surface."
---

# Control API

Default base URL: `http://127.0.0.1:8010`.

## Reads

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | Service liveness |
| `GET` | `/projects` | Registered projects and sync health |
| `GET` | `/projects/{id}` | One project |
| `GET` | `/issues` | Paginated Issues with repeated project/state filters, search, and claimable filter |
| `GET` | `/issues/{id}` | One Issue with dependencies and block reasons |

`GET /issues` accepts repeated `project_id` and `state`, plus `query`,
`claimable`, `page`, and `page_size` (maximum 200). Its state counts use the
project and search scope before state filtering so the UI can switch states
without a second count model.

## Commands

Every command requires `Idempotency-Key`.

| Method | Path | Body |
| --- | --- | --- |
| `POST` | `/projects` | `{remote}` |
| `PATCH` | `/projects/{id}` | `{enabled}` |
| `POST` | `/projects/{id}/sync` | none |
| `PUT` | `/issues/{id}/analysis` | expected analysis version, complete dependency Issue-number set, optional manual hold |
| `POST` | `/issues/{id}/claim` | expected scheduling version |
| `POST` | `/issues/{id}/release` | expected scheduling version and reason |

Blocked commands return `{status, reason_code, explanation, details}`. A caller
must re-read on analysis or scheduling version conflicts.

## Webhook

`POST /webhooks/github` verifies `X-Hub-Signature-256`, accepts GitHub `issues`
events, deduplicates `X-GitHub-Delivery`, and triggers an exact REST Issue
refresh. `ping` receives an empty success response. Other event types are not
part of the current adapter.

No GraphQL, PR, check, review, comment-review, lease, worker, queue, or scheduler
cycle endpoint is implemented.

## CLI

Current commands are `kairota serve`, `kairota health`, and
`kairota projects register|list|show|sync`. Normal startup manages the internal
database automatically; no migration command is part of the user workflow.
