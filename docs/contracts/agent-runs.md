---
doc:
  updated_at: 2026-07-08
  category: contract
  status: draft
  audience: ai
  keywords: [agent, worker, run, lifecycle]
  description: "Defines planned worker and agent run facts for audit and recovery."
---

# Agent Runs

Status: draft. No agent-run store is implemented yet.

## Planned Role

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

## Lifecycle

`planned -> claimed -> running -> reporting -> closed`

The spawning agent or scheduler owns lifecycle cleanup. Completed, idle, or
superseded agents should not remain open.

## Privacy

Do not store private runtime ids, local machine paths, local clocks, or private
environment values in public issue, PR, or project text.
