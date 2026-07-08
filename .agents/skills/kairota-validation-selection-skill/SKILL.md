---
name: kairota-validation-selection-skill
description: "Kairota validation selection for docs, skills, governance checks, scheduler logic, work-item contracts, APIs, UI, adapters, and implementation changes. Use when choosing narrow checks, one-time validation versus recurring tests, or completion evidence. Not for writing product code by itself."
---

# Kairota Validation Selection Skill

Choose the narrowest checks that prove the changed contract.

## Rules

- Follow `docs/validation/baseline.md`.
- Validate the behavior or contract changed by the task.
- Prefer deterministic checks for repeatable governance rules.
- Do not add recurring tests for one-time migration evidence unless they will
  catch future regressions.
- For UI work, include user-perspective validation when the change affects a
  primary workflow or introduces a new screen.
- Report blocked validation with the exact command and blocker.

## Levels

| Level | Use when | Checks |
| --- | --- | --- |
| Docs | durable docs or root rules changed | governance check, `git diff --check` |
| Skills | skill trigger, workflow, or metadata changed | governance check, system skill validator, `git diff --check` |
| Contracts | planned or implemented schema/API/scheduler contracts changed | focused unit tests once product code exists |
| Scheduler | claim, lease, dependency, conflict, or reconcile logic changed | deterministic unit tests and replay cases |
| UI | queue, dashboard, decision, or cost surface changed | component tests and browser/user-path validation |
| Integration | GitHub, Codex, CI, webhook, or MCP adapter changed | mocked API tests plus one bounded smoke when safe |

## Current M0 Commands

```bash
python .agents/checks/check_ai_governance.py
git diff --check
```

Product tests are added after product runtime code exists.
