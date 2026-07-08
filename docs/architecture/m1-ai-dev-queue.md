---
doc:
  updated_at: 2026-07-08
  category: architecture
  status: mixed-current-planned
  audience: ai
  keywords: [m1, ai-dev-queue, scheduler, implementation-plan]
  description: "Details the planned M1 AI Dev Queue architecture and implementation slices."
---

# M1 AI Dev Queue Detailed Design

Status: mixed current and planned. M1.0 runtime foundation is being implemented;
M1 scheduler, GitHub sync, worker runtime, and queue data flows are not
implemented yet.

## Purpose

M1 replaces GitHub Project as the durable scheduler for AI development work.
GitHub is the first repository adapter, but Kairota owns scheduler truth through
provider-neutral contracts.

## Current Facts

- M0 has root rules, routing docs, initial contracts, skills, and governance checks.
- Runtime foundation files now include backend, frontend, configuration, and
  migration scaffolding.
- There is no product database schema, scheduler, worker runtime, product API,
  MCP server, webhook receiver, or GitHub adapter implementation yet.
- Existing M1 capability expectations are defined in `MILESTONES.md`.

## M1 Outcomes

M1 is done when a single local operator can:

- create or sync work items with priority, risk, dependencies, expected touch,
  conflict keys, acceptance, validation, and status;
- run deterministic scheduler planning that records assigned and rejected work;
- claim ready work with leases and active conflict locks;
- record worker runs and validation evidence;
- sync GitHub issue, PR, check, and review summaries through the GitHub adapter;
- use a queue UI showing ready, blocked, running, waiting, failed, and done work;
- reconcile stale leases, external repository state, and failed runs without
  losing audit history.

## M1 Non-Goals

- Cost trend dashboards beyond small duration fields needed beside work.
- Cross-project experience registry.
- Consultant agents.
- Hosted multi-tenant deployment.
- Full document editing, source hosting, or CI execution.
- Direct merge automation that bypasses repository gates.
- Full transcript, terminal log, or private file storage by default.

## Decision Summary

| Area | M1 choice | Rationale |
| --- | --- | --- |
| Runtime shape | Python API and domain services, TypeScript React UI, Postgres store | Keeps scheduler logic close to typed contracts while allowing a rich operational UI. |
| Backend API | FastAPI with Pydantic models | Produces OpenAPI read/write contracts early and keeps REST, CLI, and MCP boundaries explicit. |
| Persistence | PostgreSQL with SQLAlchemy and Alembic | Matches lease and lock safety requirements and gives durable migrations from the first schema. |
| Scheduler execution | Postgres-backed scheduler cycle with row locks, active lock rows, and event records | Gives deterministic, inspectable behavior without a resident workflow engine in M1. |
| Workflow engine | Postgres outbox and reconciler first; Temporal deferred | M1 workflows are bounded enough to avoid another service while preserving a future escalation path. |
| Frontend | Vite React TypeScript SPA using API read models | Provides an operational UI without requiring a second server runtime. |
| GitHub adapter | GitHub App as the target integration model; local token mode may exist behind the same adapter contract | GitHub App supports least-scoped permissions and webhook/check integration, while the adapter boundary prevents GitHub from becoming scheduler truth. |
| Webhooks | Optional receiver after signature verification and idempotent event storage | Polling can bootstrap M1; verified webhooks reduce staleness once configured. |
| MCP | Add after REST commands are stable, with bounded actions only | Avoids exposing raw mutation surfaces to agents before the control contract is proven. |
| Auth | Single-operator local mode in M1; remote and multi-user auth deferred | Fits local-first scope and avoids speculative hosted SaaS design. |

## External Benchmarks

- PostgreSQL documents `FOR UPDATE SKIP LOCKED` for skipping rows that cannot be
  locked immediately during concurrent selection:
  <https://www.postgresql.org/docs/current/sql-select.html>
- PostgreSQL row-level locks are transaction-scoped and block writers or lockers
  of the same row, which fits claim and lease safety:
  <https://www.postgresql.org/docs/current/explicit-locking.html>
- FastAPI is based on Python type hints and OpenAPI, which fits contract-first API
  development:
  <https://fastapi.tiangolo.com/>
- SQLAlchemy is a mature Python SQL toolkit and ORM:
  <https://docs.sqlalchemy.org/>
- Alembic is the SQLAlchemy migration tool:
  <https://alembic.sqlalchemy.org/>
- Vite is a frontend build tool for modern web projects and supports React
  templates:
  <https://vite.dev/guide/>
- GitHub recommends validating webhooks with `X-Hub-Signature-256` and HMAC-SHA256:
  <https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries>
- GitHub webhook events provide issue, pull request, check, status, review, and
  comment change notifications:
  <https://docs.github.com/en/webhooks/webhook-events-and-payloads>
- GitHub Checks expose check runs and check suites as repository integration data:
  <https://docs.github.com/rest/checks>
- GitHub commit statuses can also affect pull request status:
  <https://docs.github.com/en/rest/commits/statuses>
- GitHub GraphQL exposes pull request review thread state needed for review gates:
  <https://docs.github.com/en/graphql/reference/pulls>
- Temporal provides durable execution for crash-proof workflows, but it is deferred
  until Kairota has long-running workflow needs that exceed a Postgres outbox:
  <https://docs.temporal.io/>

## Planned System Shape

```text
GitHub issue, PR, check, and review data
        |
        v
GitHub adapter normalizers
        |
        v
Kairota contracts in Postgres
        |
        +--> scheduler cycle -> leases -> conflict locks -> worker runs
        |
        +--> REST read models -> queue UI
        |
        +--> REST commands -> outbox -> adapter mutations
        |
        +--> reconciler -> stale lease, PR, check, and review updates
```

Adapters may read external state and request bounded mutations. They do not own
work item status, scheduling eligibility, leases, or conflict locks.

## Planned Data Model

These are planned tables or equivalent persisted records. Names may change during
implementation, but the ownership boundaries should not.

| Record | Owns |
| --- | --- |
| `work_items` | Title, status, priority, risk, work type, autonomy mode, acceptance, validation, source link, expected touch summary. |
| `work_item_dependencies` | Directed dependency edges between Kairota work items. |
| `work_item_conflict_keys` | Explicit locks requested by a work item. |
| `repositories` | Provider-neutral repository identity, provider, default branch, sync status. |
| `external_refs` | Provider, external type, external id, URL, and link to a Kairota record. |
| `scheduler_guards` | One persisted guard row per queue or project used to serialize scheduler cycles. |
| `scheduler_cycles` | Scheduler run id, input version, counts, start/end, result. |
| `scheduler_decisions` | Work item, decision code, explanation, blocking facts, and cycle id. |
| `leases` | Work item, logical owner slot, status, fencing token, acquired/heartbeat/expires timestamps. |
| `lock_holders` | Active conflict key holder from a lease, PR, or conservative fallback. |
| `worker_runs` | Role, lifecycle, lease, result, validation evidence, public mutation summary. |
| `repo_pull_requests` | Provider-neutral PR summary, linked work item, state, draft flag, branch summary, merge state. |
| `repo_check_summaries` | Check or check-suite name, status, conclusion, required flag when known. |
| `repo_review_summaries` | Review state, unresolved count, approval state, review-gate summary. |
| `sync_cursors` | Provider, repository, sync kind, cursor, observed timestamp, last success, last failure. |
| `inbound_events` | Webhook or poll event idempotency key, source, type, action, external id, payload hash, processing status. |
| `outbox_events` | Planned adapter mutation, idempotency key, status, retry count, next attempt. |
| `audit_events` | Human-readable and machine-readable record of important state changes. |

Default storage should keep summaries, identifiers, hashes, and links. Do not
store full transcripts, full terminal logs, full review bodies, or private files
by default.

## Work Item State Model

Initial planned states:

```text
Backlog -> Ready -> Claimed -> Implementing -> PR Open -> Waiting Checks
-> Merge Armed -> Merged -> Done
```

Blocking states:

- `Needs Triage`
- `Blocked`
- `Human Decision`
- `Strict AI Review`
- `CI Failed`
- `Gate Failed`

State ownership:

- Kairota commands and scheduler rules own work item state.
- GitHub sync owns repository summaries and may trigger Kairota transitions.
- Worker runs own run lifecycle and validation evidence.
- Human actions own override, unblock, and decision records.

## Repository State Sync Model

Kairota uses external repository state as evidence, not as scheduler truth.

The sync pipeline has five steps:

1. ingest webhook or polling observations into `inbound_events`;
2. deduplicate by provider delivery id or polling idempotency key;
3. normalize payloads into provider-neutral repository summaries;
4. reduce repository summaries into proposed Kairota state transitions;
5. apply allowed transitions through Kairota state machine commands with audit.

Direct writes from GitHub payloads to `work_items.status` are not allowed.
External state may only update `external_refs`, repository summary records,
inbound event state, outbox state, and audit records before the reducer runs.

Webhook and polling roles:

- Webhooks provide low-latency observations.
- Polling is the authoritative repair path for missed, duplicated, failed, or
  out-of-order webhooks.
- A local installation may start with polling only, but the same normalizers and
  reducers must be used by both paths.

Initial subscribed or polled GitHub facts:

- issues and issue comments for source requirements and human decisions;
- pull requests for branch, draft, head SHA, state, mergeability, and merge state;
- check runs, check suites, and commit statuses for current head SHA gates;
- reviews and review threads for approval and unresolved-thread gates.

Each normalized repository summary should include:

- provider and repository id;
- provider object id and stable URL;
- source updated timestamp when provided by the provider;
- observed timestamp assigned by Kairota;
- payload hash or source version;
- current PR head SHA when the fact is PR-check or PR-review related;
- link to the Kairota work item when known;
- stale or incomplete flag when required provider facts are missing.

Retention defaults:

- keep normalized summaries and payload hashes;
- keep bounded raw event payloads only long enough for debugging failed
  normalizers;
- do not keep full comment bodies, full review bodies, transcripts, terminal
  logs, or private files by default.

## Repository State Reduction Rules

The reducer translates repository summaries into Kairota state transitions. It
must be deterministic for the same persisted summaries.

Initial rules:

| Repository fact | Planned Kairota effect |
| --- | --- |
| New linked issue | Create or link a work item in `Needs Triage` or `Backlog`; do not infer scheduling fields without Kairota triage. |
| Issue edited | Update source summary and audit; do not overwrite Kairota priority, risk, dependencies, expected touch, conflict keys, acceptance, or validation. |
| Issue closed without merged linked PR | Move to `Human Decision` unless a Kairota close command already explains the closure. |
| PR opened or synchronized | Link PR summary, set or retain PR-derived locks, and move eligible implemented work toward `PR Open`. |
| PR draft | Keep the work out of `Merge Armed`; surface as waiting or blocked by draft state. |
| PR head SHA changes | Mark older check and review summaries stale for gate purposes. |
| Required current-head checks pending | Surface as `Waiting Checks`; do not fail the work item. |
| Required current-head checks fail | Move or surface as `CI Failed` with check reason codes. |
| Review approval missing | Surface as waiting review when checks are otherwise acceptable. |
| Requested changes or unresolved review threads | Move or surface as `Strict AI Review` or `Gate Failed`. |
| Required checks pass and review gate passes | Move eligible PR work to `Merge Armed`. |
| PR merged | Move to `Merged`; release locks only after worker-run close or reconciliation audit. |
| PR closed unmerged | Move to `Human Decision` unless reconciliation proves no public mutation remains and the work can safely return to `Ready`. |

The reducer should never treat an issue close as `Done`. `Done` requires Kairota
completion evidence: merged or intentionally closed work, worker-run closure,
validation evidence, and lease or lock cleanup.

## Ordering, Freshness, And Repair

GitHub events can be duplicated, delayed, omitted, or observed out of order.
Kairota should treat the latest provider snapshot as stronger evidence than a
single event.

Rules:

- Idempotency key collisions with different payload hashes are sync errors.
- Older observed events cannot downgrade newer repository summaries.
- Check and review gates are evaluated only for the current PR head SHA.
- Unknown required checks or unknown review-thread state produce `Human Decision`
  or `Strict AI Review`, not `Merge Armed`.
- Failed normalizers leave failed inbound events visible for repair.
- Reconciliation can rebuild repository summaries, sync cursors, and derived PR
  locks from provider snapshots.
- Scheduler cycles read only persisted Kairota and repository summary records,
  not live provider APIs.

## Conflict Key Format

Conflict keys are logical locks, not necessarily file paths. They should be
stable, provider-neutral, and derived from repo-relative or contract-relative
facts.

Initial planned namespaces:

- `repo:<repo-key>:path:<repo-relative-glob>` for expected code or docs touch;
- `contract:<contract-name>` for shared Kairota contracts;
- `adapter:<provider>` for adapter implementation and sync behavior;
- `runtime:<component>` for backend, frontend, scheduler, or worker runtime areas;
- `governance:<area>` for AI rules, skills, privacy, or validation governance;
- `unknown:<scope>` as the conservative fallback when expected touch is missing.

External adapters may suggest conflict keys, but Kairota stores the normalized
keys and owns conflict decisions.

## Scheduler Contract

Scheduler cycles are deterministic for the same persisted input set.

Stable ordering:

1. priority;
2. risk;
3. creation order or numeric id.

Each cycle should:

1. lock the persisted scheduler guard row for the queue;
2. load worker capacity, active leases, active locks, open or merge-armed PR
   locks, dependencies, and candidate work items;
3. evaluate candidates in stable order;
4. record one scheduler decision for each assigned or rejected candidate;
5. create leases and lock holders for assigned work in the same transaction;
6. emit outbox or audit events only after persisted state is valid.

Reason codes should be machine-readable. Initial codes:

- `assigned`
- `blocked_by_dependency`
- `blocked_by_status`
- `blocked_by_conflict_key`
- `blocked_by_capacity`
- `blocked_by_missing_expected_touch`
- `blocked_by_missing_acceptance`
- `blocked_by_missing_validation`
- `blocked_by_review_gate`
- `blocked_by_ci`
- `blocked_by_human_decision`
- `blocked_by_expired_or_stale_source`

## Claim, Lease, And Lock Rules

Claims and leases are separate facts:

- claim means the scheduler selected work for a logical worker slot;
- lease means that slot currently has mutation authority;
- lock holders prevent conflicting work from being assigned in parallel.

Planned invariants:

- A public mutation command must include a valid lease id and current fencing token.
- Lease owner is a logical slot or worker identity, not a private runtime id.
- The worker must re-read the lease before branch creation, PR creation, gate
  actions, external comments, and final state updates.
- An active lock key can have only one active holder.
- Missing or ambiguous expected touch uses a conservative fallback lock.
- Expired leases are not deleted; they are closed by reconciliation with an audit event.

Postgres enforcement should include:

- transactional claim and lease creation;
- row-level locking around candidate work item selection;
- an active-lock uniqueness constraint;
- a persisted scheduler guard row locked for the duration of a planning cycle;
- state-transition checks in application code and tests;
- reconciliation that releases or supersedes stale locks only after reading
  repository and worker-run state.

## Reconciliation Rules

The reconciler is responsible for recovery, not primary scheduling.

It should:

- expire stale leases and record why;
- reconcile PR state, check summaries, review summaries, and merge state;
- move work back to `Ready` only when no public mutation or active PR exists;
- move uncertain work to `Human Decision` or `Strict AI Review`;
- rebuild derived lock holders from active leases and open or merge-armed PRs;
- retry idempotent outbox events with bounded backoff;
- preserve failed inbound event records for inspection.

## Quality Gates Against Demo Shortcuts

These shortcuts are not acceptable for M1 implementation:

- directly mapping GitHub labels to scheduler truth without Kairota fields;
- treating issue open or closed state as the work item state;
- treating any historical successful check as sufficient after a PR head SHA change;
- treating one webhook delivery as authoritative without polling repair;
- storing raw external payloads, comments, logs, or transcripts as the default
  data model;
- allowing public mutations without lease and fencing-token checks;
- releasing conflict locks only because a worker lease expired while a PR is
  still open or merge-armed;
- hiding stale, incomplete, or failed sync state from the UI.

## GitHub Adapter Boundary

The GitHub adapter converts external repository state into Kairota contracts.

Initial reads:

- issues as source links and requirements;
- pull requests as repository summaries linked to work items;
- check runs, check suites, and commit statuses as check summaries;
- reviews and review threads as review-gate summaries;
- labels only when mapped through Kairota-owned fields.

Initial writes:

- none required for the smallest scheduler slice;
- later M1 writes may create bounded comments, labels, branches, or PR metadata
  only through outbox commands with idempotency keys and valid leases.

Webhook handling:

- verify the signature before processing;
- store an idempotency key and payload hash;
- normalize payloads into Kairota records;
- keep raw payload retention bounded and configurable;
- support polling as a baseline fallback when webhooks are unavailable.

## API Surface

REST is the first stable integration surface. API handlers call domain services;
they do not mutate tables directly.

Planned read resources:

- `GET /work-items`
- `GET /work-items/{id}`
- `GET /queue/summary`
- `GET /scheduler/cycles/{id}`
- `GET /worker-runs/{id}`
- `GET /repositories/{id}`
- `GET /events`

Planned command resources:

- `POST /work-items`
- `POST /work-items/{id}/triage`
- `POST /scheduler/cycles`
- `POST /work-items/{id}/claim`
- `POST /leases/{id}/heartbeat`
- `POST /worker-runs`
- `POST /worker-runs/{id}/close`
- `POST /repositories/{id}/sync`
- `POST /webhooks/github`

Command rules:

- repeated or public mutations require an idempotency key;
- blocked commands return machine-readable reason codes;
- adapter-specific payloads stay behind adapter endpoints or normalized event records;
- write responses include current state and next allowed actions.

## CLI Surface

The CLI exists for local administration and validation, not as a separate product
contract.

Planned commands:

- initialize or migrate the database;
- create or inspect work items;
- run one scheduler cycle;
- sync one repository;
- print queue summary;
- run reconciliation once;
- run smoke validation.

## UI Surface

The first UI is a queue workbench.

Primary regions:

- Ready work, ordered by scheduler priority.
- Running workers with lease age, heartbeat state, and lock keys.
- Blocked work with reason codes.
- Waiting repository checks or review.
- Human or delegated AI decision inbox.
- Recent events and failures.

Required row details:

- work item title, priority, risk, status, work type;
- dependency and conflict indicators;
- source link and PR summary when present;
- check and review summary;
- lease or worker-run summary;
- next allowed action.

The UI should be operational and dense. It should not introduce project-management
features until scheduler correctness is visible and trustworthy.

## Validation Strategy

M1 validation should prove contracts, not only happy paths.

Planned checks:

- domain unit tests for state transitions and reason codes;
- scheduler replay tests proving deterministic order;
- Postgres integration tests for claim, lease, expiry, and active-lock uniqueness;
- adapter normalizer tests with bounded fixture payloads;
- webhook signature and idempotency tests;
- repository state reducer tests for issue, PR, check, review, stale head SHA,
  unmerged close, and merged close cases;
- reconciliation replay tests that recover from missed, duplicated, failed, and
  out-of-order events;
- REST contract tests from OpenAPI examples;
- UI component tests for queue sections and blocked reasons;
- browser smoke test for the queue workbench once UI exists;
- governance checks and whitespace checks for docs.

## Implementation Slices

### M1.0 Runtime Foundation

Deliver:

- backend package layout;
- frontend package layout;
- database migration tooling;
- local configuration template with no secrets;
- initial developer commands.

Validate:

- import and lint checks;
- empty app health check;
- migration creates and drops an empty baseline.

### M1.1 Core Schema And Contracts

Deliver:

- migrations for work items, dependencies, conflict keys, leases, locks,
  worker runs, repository summaries, events, and outbox;
- typed domain models and Pydantic API models;
- state and reason-code enums.

Validate:

- migration tests;
- model serialization tests;
- database constraints for required ownership boundaries.

### M1.2 State Machine And Scheduler Planner

Deliver:

- pure scheduler planning function;
- eligibility checks for dependencies, status, expected touch, acceptance,
  validation, capacity, and conflicts;
- recorded scheduler decisions.

Validate:

- deterministic replay fixtures;
- blocking reason tests;
- stable ordering tests.

### M1.3 Claims, Leases, And Conflict Locks

Deliver:

- transactional claim command;
- lease heartbeat and expiry;
- active lock holder persistence;
- reconciliation of stale leases and locks.

Validate:

- real Postgres concurrency tests;
- duplicate claim prevention;
- lock conflict prevention;
- expired lease recovery paths.

### M1.4 REST API And CLI

Deliver:

- read models for queue summary and work item detail;
- bounded command endpoints with idempotency keys;
- local CLI wrappers for create, inspect, schedule, claim, sync, and reconcile.

Validate:

- REST contract tests;
- CLI smoke tests against a local test database;
- blocked command response tests.

### M1.5 GitHub Sync Adapter

Deliver:

- adapter interface;
- GitHub issue, PR, check, status, review, and review-thread normalizers;
- polling sync for one configured repository;
- webhook receiver with signature verification when configured;
- inbound event idempotency.
- repository state reducer and transition audit records;
- sync cursors and stale-summary indicators.

Validate:

- fixture-based normalizer tests;
- webhook signature tests;
- sync replay idempotency tests;
- reducer tests for issue close, PR open, PR synchronize, failed checks, stale
  checks, requested changes, unresolved threads, merged PR, and unmerged PR close;
- reconciliation tests for missed, duplicated, failed, and out-of-order events;
- privacy checks for stored payload summaries.

### M1.6 Worker Run Lifecycle

Deliver:

- worker run creation, heartbeat, reporting, and close commands;
- validation evidence recording;
- public mutation guard requiring valid lease and fencing token.

Validate:

- lifecycle state tests;
- mutation-without-lease rejection;
- stale fencing token rejection.

### M1.7 Queue Workbench UI

Deliver:

- queue summary screen;
- sections for ready, running, blocked, waiting, failed, and done work;
- work item detail drawer or route;
- decision inbox;
- recent events and failures.

Validate:

- component tests for each section;
- browser smoke test for loaded queue data;
- responsive checks for dense operational layout.

### M1.8 Hardening And M1 Exit

Deliver:

- reconciliation dashboard signals;
- seeded demo data;
- documented setup and validation commands;
- M1 acceptance checklist.

Validate:

- end-to-end local smoke: create or sync item, schedule, claim, record run,
  reconcile, and view in UI;
- failure-path smoke: blocked dependency, conflict lock, expired lease, CI failed,
  and review gate;
- governance and docs checks.

## Definition Of Done For M1

- Scheduler truth is stored in Kairota-owned tables.
- GitHub state is normalized into Kairota contracts before scheduler use.
- Ready, blocked, running, waiting, failed, and done states are visible in UI.
- Claims require leases and leases create active conflict locks.
- Stale leases and failed sync events are recoverable and auditable.
- Validation includes deterministic scheduler tests and real Postgres lock tests.
- Public docs and examples avoid local-only or private information.

## Open Questions After This Design

- Exact API path names may change during implementation if OpenAPI review finds
  clearer command boundaries.
- MCP action names should wait until REST commands and permission rules are stable.
- Temporal or another durable workflow engine should be reconsidered only after
  M1 shows workflows that are too long-running or failure-prone for the outbox.
- GitHub App setup can be the target integration model, but local development may
  need a temporary token mode behind the same adapter contract.
