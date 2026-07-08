---
name: kairota-docs-update-skill
description: "Kairota docs and skill governance. Use for README, AGENTS, MILESTONES, docs/README.md, docs architecture/design/interfaces/contracts/validation/governance, repo skills, owner selection, metadata, link drift, compression review, or moving AI workflow rules into skills. Not for product code implementation or public GitHub writes."
---

# Kairota Docs Update Skill

Documentation only. Optimize for AI readers, owner clarity, and low context cost.

## Rules

- Follow root `AGENTS.md`.
- Do not invent implemented commands, APIs, schemas, files, services, or behavior.
- Mark unimplemented material as `planned`, `draft`, `intended`, or `not implemented yet`.
- Do not expose secrets, local paths, proxy values, private config, private user state, or local-only environment details.
- Remove repeated caveats, vague prose, duplicate catalogs, and low-value explanation.
- Use `skill-creator` before creating or materially editing `.agents/skills/*/SKILL.md`.
- Re-read edited docs as the target AI reader and shorten again before finishing.

## Four Layers

| Layer | Owns | Do not put here |
| --- | --- | --- |
| `AGENTS.md` | root invariants, prohibitions, repo-wide commands | workflows, catalogs, implementation detail |
| `.agents/skills/` | AI behavior, task workflows, review, validation, handoff | durable project facts |
| `docs/` | architecture, design, interfaces, contracts, validation, governance facts | instructions for how agents should work |
| `.agents/checks/`, skill scripts, tests, CI | deterministic enforcement | subjective judgment |

If a sentence tells an AI how to work, put it in a skill. If it states what
Kairota is, owns, exposes, stores, validates, or plans, put it in the owner doc.

## Reader Scenario Gate

Before editing, answer:

- What future task needs this content?
- Which keyword, path, command, field, or API should find it?
- What action or decision should change after reading it?
- Could the intent be misunderstood or overgeneralized?
- Is this the right abstraction level?

If no concrete reader scenario exists, delete, shorten, or reject the content.

## Docs Taxonomy

Use `docs/README.md` as the routing index. Use these categories:

| Directory | Category | Owns |
| --- | --- | --- |
| `docs/architecture/` | `architecture` | System shape, boundaries, long-term tradeoffs |
| `docs/design/` | `design` | UI, visual system, product interaction design |
| `docs/interfaces/` | `interface` | API, CLI, MCP, webhook, adapter surfaces |
| `docs/contracts/` | `contract` | Work item, scheduler, worker, cost, experience, event contracts |
| `docs/standards/` | `standard` | Naming, logging, formatting, documentation standards |
| `docs/validation/` | `validation` | Baselines, smoke checks, acceptance matrices |
| `docs/governance/` | `governance` | Privacy, ownership, authority, public-text policy |

Use only `index|architecture|design|interface|contract|standard|validation|governance`
as `doc.category`.

## Metadata

Every durable doc uses:

```yaml
---
doc:
  updated_at: YYYY-MM-DD
  category: index|architecture|design|interface|contract|standard|validation|governance
  status: current|mixed-current-planned|draft|local-only
  audience: ai|human|both
  keywords: [short-kebab-case]
  description: "One sentence under 120 characters."
---
```

## Flow

1. Identify reader scenario and expected action.
2. Choose the layer and owner doc.
3. Read the owner doc and necessary evidence.
4. Update, create, move, split, delete, reject, or defer.
5. Update metadata, `docs/README.md`, and internal links.
6. Compression review: remove repeated, speculative, or wrong-level content.
7. Run the narrowest check.

## Validation

Use:

```bash
python .agents/checks/check_ai_governance.py
git diff --check
```
