---
doc:
  updated_at: 2026-07-08
  category: validation
  status: current
  audience: ai
  keywords: [m1, exit, acceptance, smoke]
  description: "Defines the M1 exit acceptance checklist and evidence commands."
---

# M1 Exit Checklist

Status: current. M1 is accepted when the checks below pass on the branch being
merged.

## Acceptance Evidence

| Requirement | Evidence |
| --- | --- |
| Scheduler truth is stored in Kairota tables | migrations, model constraints, scheduler and claim tests |
| GitHub state is normalized before scheduler use | GitHub normalizer, webhook, sync, and reducer tests |
| Queue states are visible | `kairota demo seed`, `kairota queue workbench`, frontend tests, browser smoke |
| Claims require leases and locks | claim tests and M1 exit smoke |
| Worker runs record validation evidence | worker run tests and M1 exit smoke |
| Stale leases and failed sync are recoverable or visible | `kairota smoke m1-exit`, queue recovery signals |
| Public examples avoid local-only information | governance check and public-text review |

## Required Commands

```bash
ruff check src tests migrations
mypy src
python -m pytest
python .agents/checks/check_ai_governance.py
git diff --check
```

Frontend:

```bash
cd web
npm run test
npm run build
```

M1 exit smoke after installing the package and migrating a local database:

```bash
kairota demo seed
kairota queue workbench
kairota smoke m1-exit
```

## Manual Review

- PR is not draft.
- Local validation output is included in the PR description.
- AI review is requested before merge.
- Any actionable review comments are resolved before merge.
- If no remote CI exists, local validation commands are the merge gate.
