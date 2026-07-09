# Kairota

Kairota is a planned personal AI work control plane.

The first product slice replaces GitHub Project as the durable scheduler for
AI-assisted development. GitHub is the first adapter, not the architecture
boundary. Kairota will own work items, dependencies, claims, leases, conflict
locks, worker runs, repository check summaries, and a compact UI that shows what
is ready, blocked, running, waiting, or done.

Future slices may add cost monitoring, project-management surfaces, cross-project
experience sharing, and consultant-style agents.

## Status

M1 AI Dev Queue MVP is implemented. Current runtime code includes the FastAPI
API, CLI, Alembic migrations, Vite React queue workbench, core database schema,
Pydantic contracts, work item state machine, deterministic scheduler planner,
claim/lease/conflict-lock services, worker run lifecycle, GitHub sync boundary,
repository registration, repository-scoped ready queues, worker reporting, M1
exit smoke checks, and queue recovery signals.

M1.9 managed-project dogfood onboarding is active. Kairota now runs as a local
service that other projects can register with, while the managed project's AI
uses `skills/kairota-managed-project` to triage synced issues, define
dependencies and conflict keys, query ready work, claim leases, and report worker
progress. `claim-next` accepts a project worker cap so managed-project AI loops
can avoid over-dispatching workers. The UI renders API data or an empty
unavailable state; product code no longer falls back to fake queue data. Demo
seed data remains a development fixture only.

## Current Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check src tests migrations
mypy src
kairota health
kairota serve
kairota repositories register --remote <github-owner>/<github-repo> --idempotency-key <key>
kairota sync repository <repository-id> --idempotency-key <key>
kairota work-items triage <work-item-id> --idempotency-key <key>
kairota queue ready --repository-id <repository-id>
kairota queue claim-next --repository-id <repository-id> --owner <worker> --max-active-leases <cap> --idempotency-key <key>
kairota queue workbench
kairota smoke m1-exit
python .agents/checks/check_ai_governance.py
git diff --check
```

Opt-in live GitHub dogfood validation creates and closes temporary issues:

```bash
python .agents/checks/live_github_dogfood.py --repo <github-owner>/<github-repo>
```

Frontend:

```bash
cd web
npm install
npm run test
npm run build
```

Advanced migration command:

```bash
alembic upgrade head
```

Normal local use does not run this manually. Kairota applies migrations
automatically before database access.

Local API service:

```bash
kairota serve
```

Kairota uses an internally managed local SQLite database by default and applies
migrations automatically before database access. `KAIROTA_DATABASE_URL` and
manual `alembic` commands are advanced maintenance overrides, not normal setup.

The default local API base URL is built into Kairota. Managed projects and the
web app use that default unless an advanced deployment overrides it. The API
allows common local Vite origins by default; override
`KAIROTA_CORS_ALLOW_ORIGINS` with a JSON array only when the web app runs from a
non-default local origin.

## Use Kairota From Another Project

Use this flow when a separate GitHub repository wants Kairota to schedule its
issues.

1. Prepare and start the Kairota service.

   ```bash
   python -m pip install -e ".[dev]"
   kairota serve
   ```

   Normal local use does not require a database URL or manual migration.
   Kairota stores scheduler state in its own local database and migrates it
   automatically. Optional environment:

   - `KAIROTA_GITHUB_TOKEN`: GitHub token for repository sync.
   - `KAIROTA_DATABASE_URL`: advanced override for the managed database.
   - `KAIROTA_CORS_ALLOW_ORIGINS`: advanced override for non-default web origins.

2. Start the web UI for human progress review.

   ```bash
   cd web
   npm install
   npm run dev
   ```

   The web UI uses Kairota's built-in default API base URL.

3. Install the managed-project skill into the other project.

   Copy `skills/kairota-managed-project/` into the managed project's AI skill
   location, or install it through the agent runtime's configured skill
   mechanism. The synced dogfood copy in `.agents/skills/kairota-managed-project/`
   is for Kairota's own development agents.

4. Configure the managed project.

   The managed-project skill assumes Kairota's built-in default API base URL.
   Record an explicit service URL only for a non-default Kairota deployment.
   Choose and record a project worker cap, for example `<worker-cap>`. Keep the
   returned `repository_id` in local ignored project notes or handoff context;
   workers need it for scoped queries and claims.

5. Register the managed GitHub repository once.

   ```bash
   curl -X POST "<default-kairota-api-base-url>/repositories" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-register-key>" \
     -d '{"remote":"<github-owner>/<github-repo>"}'
   ```

   Equivalent local CLI command when running inside the trusted Kairota
   environment:

   ```bash
   kairota repositories register --remote <github-owner>/<github-repo> \
     --idempotency-key <stable-register-key>
   ```

6. Sync GitHub issues into Kairota.

   ```bash
   curl -X POST "<default-kairota-api-base-url>/repositories/<repository-id>/sync" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-sync-key>" \
     -d '{"mode":"issues","issue_state":"open","max_pages":1}'
   ```

   Use `mode=issues` for managed-project onboarding. It syncs bounded GitHub
   issues without fetching repository-wide pull requests, checks, or review
   summaries. Optional filters include `labels`, `issue_numbers`, `since`,
   `issue_state`, and `max_pages`. GitHub webhook intake is implemented, but
   true external delivery requires an environment with a reachable webhook
   endpoint. Polling sync is the local default.

7. Tell the managed project's main AI to start completing issues with Kairota.

   The normal user prompt is: use the installed Kairota managed-project skill to
   complete this repository's GitHub issues. From that point, the managed
   project's main AI owns the loop. It reads project instructions, syncs current
   issue facts, checks whether issues already have Kairota triage facts, and
   only starts scheduling after dependencies and conflict keys are understood.

8. Let the managed project's main AI triage synced issues when needed.

   The managed project's AI, not Kairota, analyzes issue meaning and defines
   dependencies, conflict keys, readiness, priority, risk, expected touch,
   acceptance, and validation. Submit those facts through triage:

   ```bash
   curl -X POST "<default-kairota-api-base-url>/work-items/<work-item-id>/triage" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-triage-key>" \
     -d '{"status":"ready","dependency_ids":["<dependency-work-item-id>"],"conflict_keys":["<stable-conflict-key>"],"expected_touch":"<paths-or-surfaces>","acceptance":"<observable done condition>","validation":"<checks to run>"}'
   ```

   Scheduler gates are intentionally small: status `ready`, all dependency work
   items `done`, remaining worker capacity, and no active conflict-key lock.
   Review, CI, expected touch, acceptance, validation, risk, and work type are
   management facts, not dependency-satisfaction gates. Triage updates are
   patch-like: omitted fields preserve existing scheduling facts. Send an empty
   list only when a dependency or conflict list should be cleared.

9. Query and claim ready work with the project worker cap.

   ```bash
   curl "<default-kairota-api-base-url>/queue/ready?repository_id=<repository-id>"

   curl -X POST "<default-kairota-api-base-url>/queue/claim-next" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-claim-key>" \
     -d '{"repository_id":"<repository-id>","owner":"<agent-or-worker-id>","max_active_leases":<worker-cap>}'
   ```

   If the claim response is `blocked_by_capacity`, do not start another worker.
   Wait for an active lease to close or expire, then claim again with a fresh
   idempotency key.

10. Run the worker under the lease and report progress.

   Create a worker run with the claimed `work_item_id`, `lease_id`, and
   `fencing_token`. Report validation evidence, public mutations, PR links, CI
   state, review comments, or blockers through the worker-run endpoints. Close
   the worker run to release the lease and conflict locks.

11. Complete work.

    For synced GitHub issue work, the dependency-satisfying completion signal is
    the GitHub issue becoming closed and Kairota syncing that issue to `done`.
    Closing a PR, receiving review comments, or passing CI can be recorded for
    project management, but those facts do not satisfy downstream dependencies.
    For non-PR work, close the worker run with result `done` under the active
    lease and fencing token; Kairota can transition that work item to `done`
    without waiting for a linked PR.

12. Repeat until no issue can progress.

    The main AI continues querying ready work and assigning workers up to the
    recorded cap. If only untriaged issues remain, it returns to dependency
    analysis. If only blocked or capacity-limited issues remain, it reports the
    exact reason instead of inventing work.

13. Keep humans on the web workbench.

    Humans use the web UI to watch ready, running, blocked, waiting, failed, and
    done work, plus decision inbox and recovery signals. The managed project's
    AI remains responsible for issue interpretation and worker assignment.

## Docs

Start with `docs/README.md`.

Durable project facts live in `docs/`. AI workflows live in `.agents/skills/`.
Installable managed-project skills live in `skills/`. Root invariants live in
`AGENTS.md`.
