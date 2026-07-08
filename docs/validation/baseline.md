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
lifecycle commands, and queue workbench UI are implemented. MCP and M1 exit
hardening are not implemented yet.

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

## Skill Validation

When creating or editing a skill, run the system skill validator if available:

```bash
python <skill-creator>/scripts/quick_validate.py .agents/skills/<skill-name>
```

Use the local installed `skill-creator` path for `<skill-creator>`; do not write
machine-specific paths into public docs.

## Future Checks

Add M1 exit smoke checks for create or sync, schedule, claim, run reporting,
reconciliation, and UI visibility when hardening lands.
