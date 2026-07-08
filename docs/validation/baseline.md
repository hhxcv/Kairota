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

M1 runtime foundation is implemented. Scheduler, work item schema, GitHub sync,
worker runtime, and queue data flows are not implemented yet.

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
npm run build
```

Migration baseline is validated by tests. Running migrations against a real
database requires `KAIROTA_DATABASE_URL`.

## Skill Validation

When creating or editing a skill, run the system skill validator if available:

```bash
python <skill-creator>/scripts/quick_validate.py .agents/skills/<skill-name>
```

Use the local installed `skill-creator` path for `<skill-creator>`; do not write
machine-specific paths into public docs.

## Future Checks

Add scheduler, integration, and browser checks when those runtime slices exist.
