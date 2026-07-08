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

Product code is not implemented yet. Validation focuses on docs, skills, and
governance.

## Checks

```bash
python .agents/checks/check_ai_governance.py
git diff --check
```

## Skill Validation

When creating or editing a skill, run the system skill validator if available:

```bash
python <skill-creator>/scripts/quick_validate.py .agents/skills/<skill-name>
```

Use the local installed `skill-creator` path for `<skill-creator>`; do not write
machine-specific paths into public docs.

## Future Checks

Add product test commands only after product runtime code exists.
