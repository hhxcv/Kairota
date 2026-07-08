---
name: kairota-development-orchestration-skill
description: "Kairota development orchestration for broad, risky, long-running, multi-agent, end-to-end, fully autonomous, scheduler, work-item, UI, or cross-project platform work. Coordinates brief, design, review, implementation routing, validation, worker lifecycle, and handoff. Not for tiny mechanical edits."
---

# Kairota Development Orchestration Skill

Coordinate a complete AI development loop. Keep the main agent focused on scope,
decisions, evidence, and integration.

## Rules

- Follow root `AGENTS.md`.
- Read `MILESTONES.md` before feature, architecture, issue, scheduler, UI, or broad docs work.
- Prefer autonomous progress. Ask the user only for missing permission, unsafe ambiguity, unavailable source data, or external state the agent cannot change.
- Use the smallest useful end-to-end slice.
- Treat `end-to-end`, `fully autonomous`, and equivalent requests as permission
  to start at the first missing phase and continue until the requested
  deliverable state is reached.
- If the request is design-only, stop after design review `PASS`.
- Do not implement product runtime code during M0 unless the user explicitly asks.
- Do not let multiple write agents edit the same files unless they use separate
  worktrees or the main agent serially merges patches.
- Treat subagent output as evidence, not a decision.
- The spawning agent owns subagent lifecycle: record the id, consume or reject
  the result, and close it when no longer needed.

## Flow

1. Confirm milestone fit and current repo state.
2. Create a compact brief with `kairota-task-brief-skill` when scope is broad,
   risky, delegated, or long-running.
3. Use `kairota-design-decision-skill` for architecture, interface, runtime,
   storage, dependency, scheduler, or long-term tradeoffs.
4. Use `kairota-design-review-skill`; revise and re-review until `PASS`.
5. Route docs and skill work through `kairota-docs-update-skill`.
6. Implement only the scoped slice.
7. Choose checks with `kairota-validation-selection-skill`.
8. Report files changed, validation, gaps, and next action.

## First-Version Product Focus

Prioritize the AI Dev Queue:

- work items;
- scheduling facts;
- deterministic planning;
- claim, lease, and conflict lock safety;
- worker run records;
- repository PR/CI/review summaries, with GitHub as the first adapter;
- UI that clearly shows ready, blocked, running, waiting, failed, and done work.

Do not implement cost monitoring, experience hub, consultant agents, or broad
project-management features until the queue core is stable. Preserve data-model
extension points only when they directly support the first queue slice.

## Output

```markdown
## Development Loop
- Milestone: <active milestone and fit>
- Brief: <created or not needed>
- Design: <skill or not needed>
- Design Review: <PASS, REVISE loop, HUMAN_REQUIRED, or not needed>
- Implementation: <scope or not applicable>
- Validation: <commands and evidence>
- Gaps: <blockers or None>
```
