---
doc:
  updated_at: 2026-07-08
  category: validation
  status: current
  audience: ai
  keywords: [validation, checks, baseline]
  description: "Lists current validation surfaces for the incubating repository."
---

# Validation Baseline

## Current Repo State

M1 runtime foundation, core schema/contracts, state machine, pure scheduler
planner, claim and lease services, REST/CLI surfaces, GitHub sync, worker run
lifecycle commands, queue workbench UI, demo seed data, recovery signals, and
M1 exit smoke checks are implemented. MCP is not implemented yet.

## Checks

```bash
python -m pytest
ruff check src tests migrations
mypy src
python .agents/checks/check_ai_governance.py
git diff --check
```

Frontend:

```bash
cd web
npm run test
npm run build
```

Migration baseline is validated by tests. Running migrations against a real
database requires `KAIROTA_DATABASE_URL`.

Browser smoke checks cover the queue workbench layout at desktop and mobile
viewports before PR merge.

M1 exit smoke:

```bash
kairota demo seed
kairota queue workbench
kairota smoke m1-exit
```

## Skill Validation

When creating or editing a skill, run the system skill validator if available:

```bash
python <skill-creator>/scripts/quick_validate.py .agents/skills/<skill-name>
```

Use the local installed `skill-creator` path for `<skill-creator>`; do not write
machine-specific paths into public docs.

## Future Checks

Add M2 cost and flow checks when cost event ingestion and reporting surfaces land.
