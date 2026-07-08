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

M1 implementation has started. The current runtime foundation includes a FastAPI
health endpoint, CLI entry point, Alembic baseline migration, and Vite React
frontend shell. Scheduler, work item schema, GitHub sync, worker runtime, and
queue data flows are not implemented yet.

## Current Commands

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check src tests migrations
mypy src
kairota health
python .agents/checks/check_ai_governance.py
git diff --check
```

Frontend:

```bash
cd web
npm install
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
