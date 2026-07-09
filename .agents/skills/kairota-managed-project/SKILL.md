---
name: kairota-managed-project
description: "Use when an AI agent in a project managed by Kairota needs to register a GitHub repository, triage synced issues, query ready work, claim scheduler leases, report worker progress, or interpret Kairota scheduler states."
---

# Kairota Managed Project Skill

Use this skill from a repository that is managed by a local Kairota service.
Kairota is the mechanical scheduler and audit ledger. The managed project's AI
is responsible for understanding the repository, defining issue dependencies,
choosing conflict keys, and doing the implementation work.

## Required Context

- Read the managed project's local AI instructions before changing files.
- Use Kairota's built-in default service base URL unless the project explicitly
  records a non-default deployment URL.
- Determine the managed project's worker cap before claiming work. Use the same
  cap on every claim attempt for that project loop.
- Do not invent a Kairota endpoint, repository id, issue dependency, conflict
  key, worker id, or lease token.
- Treat GitHub, CI, local git, and project files as external sources. Convert
  their facts into Kairota work-item fields before scheduling.

## Managed Project Loop

When the user asks the managed project's AI to start completing GitHub issues,
run this loop without waiting for more human steering unless local project rules
require it. Kairota does not run subagents by itself; the managed project's main
AI queries Kairota, claims ready work, starts workers up to the recorded cap,
and reports progress back.

1. Register the repository once with Kairota:

   ```bash
   curl -X POST "<default-kairota-api-base-url>/repositories" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-register-key>" \
     -d '{"remote":"<github-owner>/<github-repo>"}'
   ```

   When the Kairota CLI is installed in the same trusted environment, the
   equivalent local command is `kairota repositories register --remote
   <github-owner>/<github-repo> --idempotency-key <stable-register-key>`.

2. Sync issues through the configured GitHub adapter or wait for webhook intake.
   If the repository is already registered, sync first so the loop uses current
   issue close state and current repository facts.

3. Decide whether issues are already triaged. An issue is ready for scheduling
   only when Kairota has dependency ids, conflict keys, and readiness status for
   it. GitHub labels or comments may document the analysis, but Kairota triage
   facts are the scheduler input.

4. If any issue lacks triage facts, analyze the issue graph before claiming new
   work. Define:

   - dependencies on other issues or work items;
   - conflict keys for files, APIs, data migrations, or shared runtime surfaces;
   - expected touch area for workbench context;
   - acceptance and validation evidence for reporting;
   - risk, priority, work type, and autonomy mode.

5. Submit those scheduling facts back to Kairota:

   ```bash
   curl -X POST "<default-kairota-api-base-url>/work-items/<work-item-id>/triage" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-triage-key>" \
     -d '{"status":"ready","dependency_ids":["<dependency-work-item-id>"],"conflict_keys":["<stable-lock-key>"],"expected_touch":"<paths-or-surfaces>","acceptance":"<observable done condition>","validation":"<checks to run>"}'
   ```

   Kairota scheduling requires readiness, satisfied dependencies, remaining
   worker capacity, and non-conflicting locks. Expected touch, acceptance,
   validation, risk, work type, CI, and review facts are useful management data,
   but they are not scheduler gates.

6. Query ready work for the registered project:

   ```bash
   curl "<default-kairota-api-base-url>/queue/ready?repository_id=<repository-id>"
   ```

7. Claim work only through Kairota:

   ```bash
   curl -X POST "<default-kairota-api-base-url>/queue/claim-next" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-claim-key>" \
     -d '{"repository_id":"<repository-id>","owner":"<agent-or-worker-id>","max_active_leases":<worker-cap>}'
   ```

   For local CLI use:

   ```bash
   kairota queue claim-next --repository-id <repository-id> \
     --owner <agent-or-worker-id> --max-active-leases <worker-cap> \
     --idempotency-key <stable-claim-key>
   ```

   If Kairota returns `blocked_by_capacity`, do not start another worker. Wait
   for an active lease to close or expire, then claim again with a fresh
   idempotency key.

8. Assign each claimed item to a worker or subagent with the claimed
   `work_item_id`, `lease_id`, and `fencing_token`. Before external mutations,
   confirm the lease is still valid and keep progress recorded through
   worker-run reporting.

9. When done, report validation, PR, review comments, CI, and merge state back
   through the Kairota worker and repository sync surfaces. For synced GitHub
   issue work, the issue closing is the completion signal that satisfies
   downstream dependencies.

10. Repeat the loop. If ready work exists, claim more until the worker cap is
    reached. If only untriaged work remains, triage it. If only blocked,
    dependency-waiting, or capacity-limited work remains, report the exact
    Kairota reason and stop launching workers.

## Scheduler Interpretation

- `needs_triage`: the managed project's AI must add scheduling facts.
- `blocked`: the project AI or a human explicitly marked the issue blocked.
- `ready`: the issue may be claimed when dependencies, capacity, and conflict
  locks allow it.
- `claimed` or `implementing`: another worker has lease authority.
- `blocked_by_capacity`: the project has reached its configured worker cap.
- `waiting_checks`: implementation is waiting on repository or CI facts for
  project management visibility.
- `ci_failed` or `review_changes_requested`: repair work is visible, but these
  are not dependency satisfaction signals.
- `done`: the synced issue is closed or Kairota has otherwise recorded done.

## Boundaries

- Kairota does not decide issue dependencies by itself.
- Kairota does not start workers by itself; the managed project's main AI does.
- Kairota does not replace GitHub, git, CI, or project-specific tests.
- Kairota does not grant permission to bypass the managed project's local
  instructions.
- If Kairota state conflicts with current repository facts, sync current facts
  first, then claim or triage.
