---
doc:
  updated_at: 2026-07-10
  category: validation
  status: current
  audience: ai
  keywords: [validation, checks, baseline]
  description: "Defines current backend, skill, UI, and dogfood validation."
---

# Validation Baseline

## Required Checks

```bash
pytest -q
ruff check src tests migrations
mypy src
python .agents/checks/check_ai_governance.py
git diff --check

cd web
npm test
npm run build
```

Backend tests cover the one-time destructive schema reset, project registration,
REST-only GitHub normalization, webhook verification/replay, sync failure and
recovery, all five states, dependency cycles, close/reopen, stale sync, versioned
claim/release, multi-project API filters, and a 24-Issue dependency graph.

UI changes additionally require Playwright observation from a user's point of
view on desktop and mobile. Validate multi-project selection, state counts,
search, pagination, details, add-project, sync errors, empty data, loading, and
responsive geometry. Inspect browser console errors and screenshots; component
tests alone are insufficient.

## Skill Validation

The public `skills/kairota-managed-project/SKILL.md` and dogfood copy under
`.agents/skills/` must be identical. Run the repository governance check and the
system skill validator after any change.

## Live Dogfood

Use Kairota itself as a registered project. Real GitHub Issue scenarios must
include root work, fan-out, fan-in, blocked work, close, reopen, release, and at
least one parallel ready wave. Delete or close temporary validation Issues after
recording evidence; no fake product records may remain.
