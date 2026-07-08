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

## Active: M1 AI Dev Queue MVP

Status: current.

Goal: replace GitHub Project for AI development scheduling while keeping the
core model repository-provider neutral.

Current slice: M1.2 State Machine And Scheduler Planner.

Expected capabilities:

- Work items with dependencies, risk, priority, expected touch, conflict keys, and status.
- Deterministic scheduler planning with leases and conflict locks.
- Worker run records.
- Repository PR, CI, and review summary sync, with GitHub as the first adapter.
- UI for ready, blocked, running, waiting, failed, and done work.

## Planned: M2 Cost And Flow Observability

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
