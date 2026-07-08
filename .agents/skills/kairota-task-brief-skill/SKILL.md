---
name: kairota-task-brief-skill
description: "Kairota task brief creation for broad, risky, delegated, parallel, long-running, end-to-end, fully autonomous, scheduler, work-item, UI, docs, or skill tasks. Produces compact Goal/Context/Constraints/Done When/Validation/Out Of Scope briefs. Not for final reports."
---

# Kairota Task Brief Skill

Create executable briefs with minimal context.

## Rules

- Follow root `AGENTS.md` and `MILESTONES.md`.
- Keep the brief short enough to paste into an issue, worker prompt, or handoff.
- Separate current facts from planned behavior.
- State what is explicitly out of scope.
- For end-to-end work, start from the first missing phase; for design-only work,
  stop after design delivery.
- Include validation before implementation starts.

## Template

```markdown
## Goal
<one outcome>

## Context
- <current repo state or source of truth>

## Constraints
- <milestone, privacy, architecture, dependency, or scope rule>

## Done When
- <observable completion criteria>

## Validation
- <checks or review evidence>

## Out Of Scope
- <what not to do>
```

## Delegation Notes

When assigning to a worker or reviewer:

- include only the files, issue, PR, or docs needed;
- state mutation permissions;
- state expected output format;
- prohibit local-only info in public text;
- require lifecycle cleanup for spawned agents.
