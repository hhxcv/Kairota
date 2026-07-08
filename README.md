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
demo seed data, M1 exit smoke checks, and queue recovery signals.

M2 cost and flow observability is the active planned milestone.

## Current Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check src tests migrations
mypy src
kairota health
kairota demo seed
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

## Docs

Start with `docs/README.md`.

Durable project facts live in `docs/`. AI workflows live in `.agents/skills/`.
Root invariants live in `AGENTS.md`.
