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
lifecycle commands, repository registration, repository-scoped scheduling,
managed-project triage, queue workbench UI, development demo seed fixtures,
recovery signals, root managed-project skill, dogfood skill sync, and M1 exit
smoke checks are implemented. MCP is not implemented yet.

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

Migration baseline is validated by tests. Normal local use applies migrations
automatically against Kairota's managed local database. `KAIROTA_DATABASE_URL`
is an advanced override for a non-default database.

Browser smoke checks cover the queue workbench layout at desktop and mobile
viewports before PR merge.

M1 exit smoke with development fixture data:

```bash
kairota demo seed
kairota queue workbench
kairota smoke m1-exit
```

Managed-project dogfood validation is automated by:

```bash
python -m pytest tests/test_managed_project_dogfood.py
python -m pytest tests/test_managed_project_complex_scheduling.py
```

This covers repository registration, GitHub issue sync, project-AI triage,
repository-scoped scheduling, capacity-limited claim-next, worker-run reporting,
and scoped workbench visibility without requiring network credentials. Detailed
dogfood observations and the opt-in live GitHub check are recorded in
`docs/validation/managed-project-dogfood.md`.

## Skill Validation

When creating or editing a skill, run the system skill validator if available:

```bash
python <skill-creator>/scripts/quick_validate.py .agents/skills/<skill-name>
```

Use the local installed `skill-creator` path for `<skill-creator>`; do not write
machine-specific paths into public docs.

Kairota public skills under `skills/` must have a matching dogfood copy under
`.agents/skills/`; `python .agents/checks/check_ai_governance.py` enforces this.

## Future Checks

Add M2 cost and flow checks when cost event ingestion and reporting surfaces land.
