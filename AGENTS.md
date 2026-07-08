# AGENTS.md

Root rules only. Detailed workflows live in `.agents/skills/`. Durable project
facts live in `docs/`. Milestone state lives in `MILESTONES.md`.

## Scope

- Applies repo-wide unless a closer `AGENTS.md` exists.
- Before subtree work, read the closest scoped `AGENTS.md`.
- If scoped and root rules conflict, stop and report the conflict.
- Use repo-root relative paths in reports, PR text, issues, and comments.

## Truth And Status

Current behavior is proven in this order:

1. code on the branch;
2. tests and validation output;
3. schemas, typed contracts, generated artifacts, and database migrations;
4. accepted ADRs or durable docs;
5. README and prose docs.

Do not invent commands, modules, APIs, files, config keys, artifacts, schemas,
or behavior. Mark unimplemented material as `planned`, `draft`, `intended`, or
`not implemented yet`.

## Product Boundary

Kairota is a planned personal AI work control plane. It is intended to manage
work items, scheduling facts, dependencies, leases, conflict locks, worker runs,
review state, repository check summaries, cost events, and cross-project
experience.

Kairota is not a domain application, generic chat app, full document editor,
hosted multi-tenant SaaS, secret manager, remote-control tool, or replacement
for Git, CI, or source repositories.

GitHub is the first planned repository adapter because it is the immediate
migration source. Codex, CI systems, local repos, mail, calendar, and other
tools are external integrations. Convert integration data into Kairota contracts
before using it as scheduler truth.

## Milestone Fit

- Read `MILESTONES.md` before issue, requirement, architecture, feature, or broad docs work.
- Serve the active milestone unless the user explicitly asks otherwise.
- Prefer the smallest useful end-to-end slice.
- During incubation, do not add product runtime code unless the user asks.

## Decision Criteria

- Do not overweight implementation cost in design or technical decisions.
- AI can execute sustained work, so favor quality, simplicity, reliability,
  extensibility, observability, and long-term maintainability.
- Prefer mature, stable, widely used open-source dependencies over custom code.
- When options are otherwise comparable, choose the lighter operational model.
- Cost still does not justify speculative scope, unused abstractions, or milestone drift.

## Architecture Principles

- Local-first personal control plane by default.
- Postgres-backed scheduler truth is expected for claim, lease, and lock safety.
- Keep adapters at the boundary; keep scheduler contracts owned by Kairota.
- Keep code high-cohesion, low-coupling, reusable where reuse removes real duplication.
- Make failure states, recovery paths, and audit events explicit.
- Avoid hidden resident processes, broad frameworks, or remote services for future guesses.

## Work Rules

- One task, one focused change.
- Broad, risky, long-running, multi-agent, or end-to-end work uses
  `kairota-development-orchestration-skill`.
- Architecture or interface decisions use `kairota-design-decision-skill` and
  then `kairota-design-review-skill`.
- Docs and skill work uses `kairota-docs-update-skill`; new or changed skills
  also use `skill-creator`.
- Do not overwrite user changes or reformat unrelated files.

## Privacy

Never commit, print, summarize, or expose secrets, tokens, cookies, credentials,
account identifiers, private endpoints, real local proxy values, machine paths,
local time zone, locale, exact local clock values, private notes, private
financial data, private account data, or private work records.

Public config stays portable. Machine-local config stays gitignored. Use
placeholders in examples. Public PRs, issues, comments, and docs use UTC or
date-only time when a timestamp is necessary.

Common leaks include absolute paths, user or home names, local time-zone strings,
local clock times, localhost or private endpoints, proxy values, config values,
and copied terminal output that contains local-only environment details.

## Docs And Skills

- README: human overview and common commands.
- `AGENTS.md`: root AI rules only.
- `.agents/skills/`: Kairota-specific AI workflows only.
- `docs/`: durable project facts: architecture, design, interfaces, contracts,
  standards, validation, and governance.
- `docs/README.md`: docs routing index.
- AI development governance has four layers: root invariants in `AGENTS.md`,
  AI workflows in `.agents/skills/`, durable project facts in `docs/`, and
  mechanical enforcement in `.agents/checks/`, skill scripts, tests, or CI.
- Developer-facing docs are AI-facing by default: concise, structured,
  action-oriented, searchable, and low-noise.

## Commands

Use existing repo commands only. Run from repo root.

```bash
python .agents/checks/check_ai_governance.py
git diff --check
```

Product build, test, and run commands are not established yet.

## Git, PRs, Reports

- Create branches, commits, PRs, issue mutations, or public comments only when explicitly requested.
- PR descriptions state what changed, why, validation, docs impact, and gaps.
- Final reports stay brief: files changed, summary, validation, gaps.
