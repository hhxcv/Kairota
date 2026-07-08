# MILESTONES

## Completed: M0 Project Incubation

Status: completed.

Goal: establish Kairota as an AI-readable repository before product runtime
implementation starts.

Done when:

- Root rules exist in `AGENTS.md`.
- Durable docs have owner metadata and a routing index.
- Initial Kairota skills guide docs, briefs, design, review, orchestration, and validation.
- A lightweight governance check verifies docs and skill basics.

Out of scope:

- Product backend, frontend, scheduler, database schema, worker runtime, or API implementation.
- Public release packaging.

## Completed: M1 AI Dev Queue MVP

Status: completed.

Goal: replace GitHub Project for AI development scheduling while keeping the
core model repository-provider neutral.

Expected capabilities:

- Work items with dependencies, risk, priority, expected touch, conflict keys, and status.
- Deterministic scheduler planning with leases and conflict locks.
- Worker run records.
- Repository PR, CI, and review summary sync, with GitHub as the first adapter.
- UI for ready, blocked, running, waiting, failed, and done work.

## Active: M1.9 Managed Project Dogfood Onboarding

Status: current.

Goal: make Kairota usable as a local service that manages other GitHub
projects, while eating its own dogfood on Kairota work.

Expected capabilities:

- Register a GitHub repository with Kairota through REST or CLI.
- Keep synced issues scoped to the registered repository.
- Let the managed project's AI define dependencies, conflict keys, expected
  touch, acceptance, validation, priority, risk, and readiness.
- Query and claim ready work by registered repository.
- Provide a root `skills/` skill that other projects can install to learn how
  to use Kairota.
- Keep a synced dogfood copy of that managed-project skill in `.agents/skills/`.
- Remove product reliance on fake queue data; UI shows API data or an empty
  unavailable state.
- Validate the managed-project loop end to end against Kairota-shaped GitHub
  issue sync and worker scheduling.

Out of scope:

- Kairota inferring issue dependencies semantically by itself.
- Replacing GitHub, CI, git, or repository-specific tests.
- MCP server exposure.
- M2 cost and flow analytics.

## Planned: M2 Cost And Flow Observability

Status: planned.

Goal: measure and improve AI development cost and throughput.

Expected capabilities:

- Task duration, worker time, repository review cycle, CI repair count, review count, and retry tracking.
- Token and model cost ingestion when the upstream tool exposes usage data.
- Estimated cost fields when exact usage is unavailable.
- Trend, waste, and optimization views.

## Planned: M3 Project Management Center

Goal: become the human-AI coordination surface for active projects.

Expected capabilities:

- Decision inbox.
- Progress and blocker reports.
- Project timeline and retrospective records.
- Agent utilization and quality views.

## Planned: M4 Cross-Project Experience Hub

Goal: collect, evaluate, adapt, and propagate reusable AI development experience
across projects.

Expected capabilities:

- Pattern, anti-pattern, skill template, governance rule, and postmortem records.
- Project adoption history.
- Consultant-style agents that review and advise other projects.
