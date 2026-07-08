---
name: kairota-design-decision-skill
description: "Kairota design and technical decision workflow. Use for architecture, scheduler, database, API, MCP, webhook, adapter, UI product flow, dependency, observability, cost model, experience hub, or long-term maintainability tradeoffs before implementation. Not for small mechanical edits."
---

# Kairota Design Decision Skill

Make decisions that preserve scheduler correctness, product clarity, and
long-term maintainability.

## Rules

- Do not overweight implementation cost. AI executes development; optimize for
  quality, simplicity, reliability, extensibility, observability, and maintainability.
- Do not design only for the immediate request. Check migration, debugging,
  recovery, operations, and ownership costs.
- Benchmark mature open-source projects, platform patterns, or industry practice
  before choosing architecture, storage, API, workflow, or dependencies.
- Prefer stable, widely used open-source software over custom builds.
- When options are otherwise comparable, choose the lighter operational model.
- Keep scheduler truth behind Kairota contracts, not external project tools.
- After drafting a design, use `kairota-design-review-skill`; revise and review
  again until `PASS`.

## Flow

1. State the decision and user value.
2. Read `AGENTS.md`, `MILESTONES.md`, and relevant owner docs.
3. Name current facts versus planned behavior.
4. Benchmark proven practice or dependency options.
5. Compare two or three viable options.
6. Choose the option with the best long-term contract and maintenance profile.
7. Name the implementation slice and validation surface.
8. Run design review.

## Output

```markdown
## Decision
<chosen approach>

## Options
- <option>: <tradeoff>

## Benchmark
- <industry practice, mature OSS, or why not applicable>

## Dependency Choice
- <reuse/custom decision and stability rationale>

## Rationale
- <quality, reliability, extensibility, observability, or maintainability reason>

## Constraints
- <milestone, contract, architecture, privacy, or boundary rule>

## Validation
- <checks needed to preserve the design>

## Review
- <PASS, REVISE loop, or HUMAN_REQUIRED>
```
