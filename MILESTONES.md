# MILESTONES

## Completed: M0 Project Incubation

Status: completed.

Goal: establish Kairota as an AI-readable repository before runtime work.

## Superseded: M1 AI Dev Queue Prototype

Status: completed, then intentionally simplified.

The prototype explored generic work items, leases, locks, worker runs, and
repository gates. M1.9 validation showed that these concepts duplicated the
single main AI's worker management and made Issue scheduling harder to operate.
The destructive M1.9 reset removes that schema and behavior; no compatibility or
data migration is required.

## Completed: M1.9 Managed Project Issue Scheduling

Status: completed.

Goal: provide reliable mechanical scheduling for other GitHub projects while
using Kairota itself as the end-to-end validation project.

Expected capabilities:

- Register one or more GitHub projects through the web, REST API, or CLI.
- Poll all GitHub Issues and accept signed Issue webhooks that trigger exact REST
  refreshes; do not use GraphQL.
- Store project-AI dependency analysis and reject missing, cross-project, self,
  or cyclic dependencies.
- Compute exactly five states: `needs_analysis`, `blocked`, `ready`,
  `in_progress`, and `closed`.
- Treat GitHub Issue `closed` as the only dependency-satisfaction fact.
- Provide a versioned atomic `ready` to `in_progress` claim and a release command
  that requires fresh analysis before redispatch.
- Block claims while project sync is unhealthy or stale.
- Show all real Issues in a project-filterable human UI with no fixture fallback.
- Ship `skills/kairota-managed-project` and an identical dogfood copy under
  `.agents/skills/`.
- Validate multi-project filtering and a dependency graph of at least 20 Issues,
  including parallel ready waves, close, reopen, block, release, and recovery.

Out of scope:

- Kairota interpreting Issue meaning or inferring dependencies.
- Worker/subagent records, worker caps, heartbeat, lease, attempt, execution,
  resume/requeue, conflict-lock, PR, CI, or review scheduling gates.
- Replacing GitHub, git, CI, the managed project's main AI, or project tests.
- Preserving the superseded prototype database.
- MCP exposure or hosted multi-tenant deployment.

## Planned: M2 Project Progress Observability

Status: planned.

Goal: add human project-management views only where they provide measurable
operational value. PR, CI, review, cost, and flow facts may be shown later, but
must remain separate from Issue scheduling eligibility.

## Planned: M3 Cross-Project Experience Hub

Status: planned.

Goal: collect and adapt reusable AI development practices across projects
without expanding the scheduler kernel.
