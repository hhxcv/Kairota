---
name: kairota-managed-project
description: "Use when a managed project's main AI must register a GitHub project, analyze Issue dependencies, reconcile in-progress work, query ready Issues, claim or release work, and interpret Kairota's five scheduling states."
---

# Kairota Managed Project

Use this skill only from the single main AI responsible for a project managed by
Kairota. Subagents do not call Kairota. Kairota synchronizes GitHub Issue facts
and performs mechanical dependency scheduling; the main AI interprets work,
manages subagents, validates results, and closes Issues.

## Fixed Service

Use `http://127.0.0.1:8010` unless the managed project explicitly records a
different deployment. Do not ask for a database URL or run migrations. Kairota
owns its internal database.

Before work, read the managed project's AI instructions and repository facts.
Do not invent a project ID, Issue ID, dependency, version, or API response.

## Initialize

1. Read `GET /projects` and find the row whose `name` matches the GitHub
   `owner/repo`.
2. If absent, register it:

   ```bash
   curl -X POST "http://127.0.0.1:8010/projects" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: register-<owner>-<repo>" \
     -d '{"remote":"<owner>/<repo>"}'
   ```

3. Keep the returned project ID in ignored local handoff context. Never commit a
   machine-specific deployment URL or generated project ID.
4. Refresh GitHub facts before the first scheduling loop:

   ```bash
   curl -X POST "http://127.0.0.1:8010/projects/<project-id>/sync" \
     -H "Idempotency-Key: sync-<project-id>-<logical-sequence>"
   ```

Kairota also polls automatically. Webhooks accelerate updates but do not replace
polling.

## Scheduling Loop

Run these steps in order. Do not dispatch new work until reconciliation and
analysis are complete.

### 1. Reconcile In-Progress Issues

Read all pages of:

```bash
curl "http://127.0.0.1:8010/issues?project_id=<project-id>&state=in_progress&page_size=200"
```

For every row, compare Kairota with subagents owned by this main AI:

- Confirmed active subagent: leave the Issue `in_progress`.
- Completed work not yet closed: validate it, then close the GitHub Issue; request
  sync if prompt convergence is needed.
- No active subagent or uncertain ownership: release the Issue before claiming
  anything else.

```bash
curl -X POST "http://127.0.0.1:8010/issues/<issue-id>/release" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: release-<issue-id>-v<scheduling-version>" \
  -d '{"expected_scheduling_version":<version>,"reason":"<why ownership cannot be confirmed>"}'
```

Release intentionally clears the old dependency analysis and returns the Issue
to `needs_analysis`.

### 2. Analyze Every Unanalyzed Open Issue

Read every page with `state=needs_analysis`. If any exist, do not claim new
work yet.

For each Issue:

1. Read its GitHub description, repository instructions, related Issues, and
   relevant code.
2. Build the project-local dependency graph. A dependency means this Issue
   cannot be completed until the predecessor GitHub Issue is closed.
3. Use only synced Issue numbers from the same project. Reject self-dependencies
   and check the whole graph for cycles.
4. Use a manual hold only for an explicit non-dependency decision that prevents
   work. Do not encode PR, CI, review, priority, risk, worker capacity, or file
   overlap as scheduler dependencies.
5. Replace the complete analysis:

   ```bash
   curl -X PUT "http://127.0.0.1:8010/issues/<issue-id>/analysis" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: analyze-<issue-id>-v<analysis-version>" \
     -d '{"expected_analysis_version":<version>,"dependency_issue_numbers":[<numbers>],"manual_hold_reason":null}'
   ```

An empty dependency list is valid only after this explicit analysis.

### 3. Select And Claim Ready Work

The main AI determines its own worker cap from its runtime and local project
rules. Kairota does not store or enforce the cap.

Read claimable ready Issues:

```bash
curl "http://127.0.0.1:8010/issues?project_id=<project-id>&state=ready&claimable=true&page_size=200"
```

Select no more Issues than the main AI has free subagent capacity. For each
selected row, claim immediately before assignment:

```bash
curl -X POST "http://127.0.0.1:8010/issues/<issue-id>/claim" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: claim-<issue-id>-v<scheduling-version>" \
  -d '{"expected_scheduling_version":<version>}'
```

Start the subagent only after claim succeeds. If startup fails, release the Issue
immediately. Give the subagent the GitHub Issue, repository instructions,
acceptance criteria, and validation requirements. Do not give it Kairota
credentials or ask it to report Kairota state.

### 4. Complete And Continue

A subagent reports only to the main AI. The main AI reviews and validates its
work using the managed project's normal process. When the Issue is genuinely
complete, close the GitHub Issue. Kairota's next webhook or poll changes it to
`closed` and recomputes dependents.

Repeat from reconciliation. Stop launching work when no free capacity exists or
no Issue is claimable. Report exact visible blockers; do not invent replacement
work.

## State Interpretation

- `needs_analysis`: dependency facts are absent or were invalidated by reopen
  or release.
- `blocked`: analysis is complete, but a dependency Issue is open or a manual
  hold exists.
- `ready`: every dependency Issue is closed and the Issue can be considered
  for claim.
- `in_progress`: the main AI claimed the Issue and is responsible for
  reconciling its assignment.
- `closed`: GitHub reports the Issue closed; it satisfies downstream
  dependencies.

`claimable_now=false` on a ready row means the project is disabled or sync is
unhealthy/stale. Refresh the project and re-read before deciding.

## Conflict And Failure Handling

- On `analysis_version_conflict` or `scheduling_version_conflict`, discard the
  stale command, re-read the Issue, and decide again.
- On `dependency_not_found`, synchronize the project and verify the Issue
  number before resubmitting.
- On `dependency_cycle`, correct the graph; never bypass the check with a
  manual hold.
- On sync `error` or `sync_stale`, do not claim. Run project sync and inspect
  the project's `last_error`.
- Reuse an idempotency key only to retry the identical logical command and body.
  A changed version, dependency set, or reason is a new command and key.
- After a main-AI restart, inability to prove active subagent ownership requires
  release. Do not assume an old `in_progress` row is safe to reuse.

## Boundaries

- GitHub Issue close is the only completion fact that satisfies dependencies.
- Kairota does not infer dependencies, run subagents, track worker state, or
  enforce concurrency.
- PR, CI, review, validation, cost, and retry data are outside current scheduler
  eligibility.
- Kairota does not replace git, GitHub, CI, project tests, or local project
  instructions.
