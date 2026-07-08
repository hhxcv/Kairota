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
progress. The UI renders API data or an empty unavailable state; product code no
longer falls back to fake queue data. Demo seed data remains a development
fixture only.

## Current Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check src tests migrations
mypy src
kairota health
kairota repositories register --remote <github-owner>/<github-repo> --idempotency-key <key>
kairota sync repository <repository-id> --idempotency-key <key>
kairota work-items triage <work-item-id> --idempotency-key <key>
kairota queue ready --repository-id <repository-id>
kairota queue claim-next --repository-id <repository-id> --owner <worker> --idempotency-key <key>
kairota queue workbench
kairota smoke m1-exit
python .agents/checks/check_ai_governance.py
git diff --check
```

Frontend:

```bash
cd web
npm install
npm run test
npm run build
```

Database migrations require `KAIROTA_DATABASE_URL` to be set:

```bash
alembic upgrade head
```

Local API service:

```bash
uvicorn kairota.api.app:app --host <host> --port <port>
```

Managed projects configure `KAIROTA_API_BASE_URL` to point at that service.
The web app uses `VITE_KAIROTA_API_BASE_URL`.

## Docs

Start with `docs/README.md`.

Durable project facts live in `docs/`. AI workflows live in `.agents/skills/`.
Installable managed-project skills live in `skills/`. Root invariants live in
`AGENTS.md`.
