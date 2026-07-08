---
doc:
  updated_at: 2026-07-08
  category: contract
  status: mixed-current-planned
  audience: ai
  keywords: [agent, worker, run, lifecycle]
  description: "Defines worker and agent run facts for audit and recovery."
---

# Agent Runs

Status: mixed current and planned. The `worker_runs` store and M1.6
create, heartbeat, report, and close commands are implemented. Runtime spawning,
automatic cleanup, MCP exposure, and exact cost ingestion are planned.

## Role

Agent runs record who worked on what, with what authority, and what happened.

## Core Facts

| Field | Purpose |
| --- | --- |
| Work Item | Schedulable unit being handled |
| Role | Worker, reviewer, scheduler, triager, repair agent, or consultant |
| Lease | Valid claim for mutation authority |
| Start / End | Duration and recovery |
| Result | Done, blocked, failed, superseded, or abandoned |
| Public Mutations | External issues, PRs, comments, branches, statuses |
| Validation | Commands or checks run |
| Cost Summary | Exact or estimated usage when available |

## Implemented Commands

| Command | Authority | Effect |
| --- | --- | --- |
| Create | Active lease id and current fencing token | Creates a running worker run and moves claimed work to `implementing`. |
| Heartbeat | Current fencing token for the run lease | Refreshes worker-run heartbeat evidence. |
| Report | Current fencing token for the run lease | Records validation, public mutation summary, and cost summary. |
| Close | Current fencing token for the run lease | Closes the run, releases the lease-held locks, and applies allowed work-item completion or blocked transitions. |

All commands use `command_requests` idempotency. Reusing the same idempotency key
with the same payload returns the stored result; reusing it with a different
payload returns `idempotency_conflict`.

## Lifecycle

`planned -> claimed -> running -> reporting -> closed`

The implemented M1.6 create command starts at `running`; `planned` and `claimed`
remain schema states for future scheduler-spawned runs. Completed, idle, or
superseded agents should not remain open.

`done` close moves a work item to `done` only after repository evidence has
already moved it to `merged`. `blocked` close moves an implementing work item to
`blocked`. Other results close the run without directly completing the work item.
Closing releases the active lease and its active lease-held conflict locks.

## Privacy

Do not store private runtime ids, local machine paths, local clocks, or private
environment values in public issue, PR, or project text.
