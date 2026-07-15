---
doc:
  updated_at: 2026-07-10
  category: architecture
  status: current
  audience: ai
  keywords: [m1, managed-issue, scheduler, implementation]
  description: "Defines the implemented five-state managed Issue scheduler."
---

# Managed Issue Scheduler Design

## Goal

Reliably answer two questions for each registered project:

1. Which GitHub Issues can start now?
2. Which Issues are analyzed, blocked, active, or complete?

## State Derivation

Kairota evaluates facts in this order:

1. GitHub Issue closed: `closed`.
2. A successful current claim exists on the Issue row: `in_progress`.
3. Dependency analysis is absent or invalidated: `needs_analysis`.
4. A manual hold exists or any dependency Issue is open: `blocked`.
5. Otherwise: `ready`.

Only dependency Issue close state and an explicit manual hold can block an
analyzed Issue. PR, CI, review, priority, risk, validation, worker, and capacity
facts do not participate.

## Commands And Versions

- Analysis replaces the complete dependency set by Issue number and optionally
  sets a manual hold. It requires `expected_analysis_version`.
- Claim atomically updates `ready` to `in_progress` when
  `expected_scheduling_version` still matches and project sync is healthy and
  recent.
- Release is valid only for `in_progress`. It clears dependencies and manual
  hold, increments both versions, and returns `needs_analysis`.
- GitHub reopen has the same invalidation behavior as release.
- GitHub close produces `closed` and recomputes all direct dependents.

Every write is idempotent. A retry reuses its original key and body. A changed
logical command uses a new key. Version conflicts require a fresh read.

## Dependency Integrity

Dependencies must be existing synced Issues in the same project. Kairota rejects
self-edges, missing Issue numbers, cross-project references, and cycles. Closed
dependencies remain visible so humans and the main AI can understand why an
Issue became ready.

## Main AI Recovery

At the start of every scheduling loop, the unique main AI lists all
`in_progress` Issues for the project and reconciles them with subagents it still
owns. Confirmed active work remains unchanged. Unknown or abandoned ownership is
released before any new claim. This prevents restart ambiguity without adding a
Kairota worker registry or heartbeat protocol.

## Synchronization

- Full polling uses GitHub REST `issues?state=all` and ignores pull-request rows.
- Webhooks support only GitHub `issues` events and trigger exact REST refresh.
- Duplicate delivery IDs with identical payloads replay safely; conflicting
  payloads are rejected.
- A GitHub/network/parser failure persists project sync health `error`.
- Polling runs in the Kairota service lifecycle and eventually repairs missed or
  out-of-order webhooks.

## Acceptance

- All five states are reachable and visible.
- Closing and reopening a dependency recomputes downstream state correctly.
- Competing stale claims cannot both move one Issue to `in_progress`.
- A 20+ Issue acyclic graph progresses through multiple parallel ready waves.
- Project filters never mix Issue identity or dependency graphs.
- No runtime or UI fallback creates synthetic Issues.
