---
name: kairota-design-review-skill
description: "Kairota design review workflow. Use after architecture, scheduler, database, API, MCP, webhook, adapter, UI product flow, dependency, observability, cost model, experience hub, or technical plan work and before implementation or design delivery. Not for post-implementation code review."
---

# Kairota Design Review Skill

Review design plans before they become implementation work or delivered design.

## Rules

- Review every architecture, scheduler, storage, API, UI, dependency, or
  cross-project platform plan before implementation or design handoff.
- Main-agent review is acceptable for low-risk plans.
- Use an independent reviewer subagent for important or bias-prone plans when
  platform policy permits.
- Treat subagent output as evidence. The main agent owns integration and cleanup.
- If review finds issues, revise the plan and review again. Do not implement or
  deliver while the verdict is `REVISE`.

## Independent Review Threshold

Use an independent reviewer when any condition is true:

- scheduler correctness, claim, lease, or conflict locking changes;
- database schema, migration, API, MCP, webhook, or adapter boundary changes;
- privacy, security, permissions, audit, recovery, or observability changes;
- dependency choice materially affects operations or maintainability;
- UI creates or materially changes a primary work surface;
- the main thread has long history, noisy context, or implementation bias.

## Checks

- Milestone fit.
- Current versus planned facts are clearly marked.
- Scheduler truth does not depend on an external project-management or repository tool.
- Failure and recovery paths are explicit.
- Privacy and public-text rules are preserved.
- Validation proves the contract, not just the happy path.
- The design avoids speculative framework growth.

## Output

```markdown
## Design Review
- Verdict: PASS | REVISE | HUMAN_REQUIRED
- Reviewer: main | subagent
- Reviewed Inputs: <paths, docs, issue, PR, or plan>
- Findings: <blocking issues first, or None>
- Required Changes: <plan edits before proceeding, or None>
- Re-review Required: yes | no
- Residual Risk: <remaining uncertainty or None>
```
