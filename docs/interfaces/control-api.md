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

Status: mixed current and planned. Health, work item, work-item triage,
repository registration, queue summary, ready queue, queue workbench,
repository-scoped claim-next with optional worker cap, scheduler cycle, direct
claim, lease heartbeat, stale lease reconciliation, worker-run lifecycle, GitHub
repository sync, GitHub webhook, development demo seed, and M1 exit smoke
surfaces are implemented. MCP and adapter-backed public mutations are not
implemented yet.

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
- Managed projects use Kairota's built-in default local base URL and use REST
  paths under that base URL. Non-default deployments may record an explicit
  override in local project configuration.

## Implemented REST Surface

| Method | Path | Status |
| --- | --- | --- |
| `GET` | `/healthz` | implemented; includes opaque database identity |
| `GET` | `/work-items` | implemented |
| `GET` | `/work-items/{id}` | implemented |
| `POST` | `/work-items` | implemented; requires `Idempotency-Key` |
| `POST` | `/work-items/{id}/triage` | implemented; requires `Idempotency-Key` |
| `GET` | `/queue/summary` | implemented |
| `GET` | `/queue/workbench` | implemented |
| `GET` | `/queue/ready` | implemented |
| `POST` | `/queue/claim-next` | implemented; requires `Idempotency-Key` |
| `POST` | `/scheduler/cycles` | implemented; requires `Idempotency-Key` |
| `POST` | `/work-items/{id}/claim` | implemented; requires `Idempotency-Key` |
| `POST` | `/leases/{id}/heartbeat` | implemented; requires `Idempotency-Key` |
| `POST` | `/reconcile/leases/expire` | implemented; requires `Idempotency-Key` |
| `GET` | `/worker-runs/{id}` | implemented |
| `POST` | `/worker-runs` | implemented; requires `Idempotency-Key` |
| `POST` | `/worker-runs/{id}/heartbeat` | implemented; requires `Idempotency-Key` |
| `POST` | `/worker-runs/{id}/report` | implemented; requires `Idempotency-Key` |
| `POST` | `/worker-runs/{id}/close` | implemented; requires `Idempotency-Key` |
| `POST` | `/repositories` | implemented; requires `Idempotency-Key` |
| `GET` | `/repositories` | implemented |
| `GET` | `/repositories/{id}` | implemented |
| `POST` | `/repositories/{id}/sync` | implemented; requires `Idempotency-Key`; accepts sync mode and issue filters |
| `POST` | `/webhooks/github` | implemented; verifies `X-Hub-Signature-256` when configured |

`GET /work-items`, `GET /queue/summary`, `GET /queue/workbench`,
`GET /queue/ready`, `POST /scheduler/cycles`, and `POST /queue/claim-next`
support repository-scoped scheduling through `repository_id`.
`POST /queue/claim-next` also accepts `max_active_leases`; when the cap is
reached it returns `blocked_by_capacity` and does not issue a lease. When
capacity remains but no candidate can be claimed, the blocked response includes
prioritized reason counts so operators can see dependency and conflict blockers
instead of only unrelated non-ready status.

`POST /repositories/{id}/sync` accepts `mode=full|issues`, `issue_state`,
`labels`, `issue_numbers`, `since`, and `max_pages`. `mode=issues` is the
bounded managed-project onboarding path; it skips repository-wide pull request,
check, and review enrichment.

Implemented command endpoints record command idempotency in
`command_requests`. Reusing the same key and payload returns the original
result; reusing the same key with a different payload returns
`idempotency_conflict`.

## Implemented CLI Surface

| Command | Status |
| --- | --- |
| `health` | implemented |
| `serve` | implemented; starts the local API with built-in defaults |
| `db-upgrade` / `db-downgrade` | implemented |
| `work-items create/list/show/triage/claim` | implemented |
| `queue summary/workbench/ready/claim-next` | implemented; `claim-next` supports `--max-active-leases` |
| `scheduler run` | implemented; supports `--repository-id` |
| `leases heartbeat` | implemented |
| `reconcile leases` | implemented |
| `worker-runs create/show/heartbeat/report/close` | implemented |
| `repositories register/list/show` | implemented |
| `sync repository` | implemented; requires `--idempotency-key`; supports issue-only onboarding filters |
| `demo seed` | implemented as a development fixture |
| `smoke m1-exit` | implemented |

## Managed Project Skill Interface

Managed projects should use the installable skill at
`skills/kairota-managed-project/SKILL.md`. That skill instructs project-local AI
agents to use the default Kairota API base URL, register their GitHub
repository, sync or receive issue events, submit patch-like triage facts, query
ready work, claim leases, and report worker progress. Kairota remains the
mechanical scheduler; dependency analysis and issue interpretation stay with the
managed project's AI.

The expected operating mode is: a human starts Kairota, registers a managed
repository, installs the managed-project skill in that repository, and tells the
repository's main AI to complete issues with Kairota. The main AI syncs current
facts, triages untriaged issues before scheduling, claims ready work up to the
project worker cap, assigns workers, and reports worker state back through the
API.

## Planned Adapter Set

- GitHub issues, PRs, checks, comments, labels, and merges as the first adapter.
- Future repository providers through the same core contracts.
- Codex or other AI worker runtimes.
- Local repository metadata.
- Future mail, calendar, and file-system inbox sources.
