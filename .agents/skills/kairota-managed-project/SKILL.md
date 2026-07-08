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
- Load the Kairota service base URL from project configuration or
  `KAIROTA_API_BASE_URL`.
- Do not invent a Kairota endpoint, repository id, issue dependency, conflict
  key, worker id, or lease token.
- Treat GitHub, CI, local git, and project files as external sources. Convert
  their facts into Kairota work-item fields before scheduling.

## Managed Project Loop

1. Register the repository once with Kairota:

   ```bash
   curl -X POST "$KAIROTA_API_BASE_URL/repositories" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-register-key>" \
     -d '{"remote":"<github-owner>/<github-repo>"}'
   ```

   When the Kairota CLI is installed in the same trusted environment, the
   equivalent local command is `kairota repositories register --remote
   <github-owner>/<github-repo> --idempotency-key <stable-register-key>`.

2. Sync issues through the configured GitHub adapter or wait for webhook intake.
   If a synced issue is missing scheduling facts, keep it in triage rather than
   claiming it.

3. Analyze each issue in the managed repository. Define:

   - dependencies on other issues or work items;
   - conflict keys for files, APIs, data migrations, or shared runtime surfaces;
   - expected touch area;
   - acceptance and validation evidence;
   - risk, priority, work type, and autonomy mode.

4. Submit those scheduling facts back to Kairota:

   ```bash
   curl -X POST "$KAIROTA_API_BASE_URL/work-items/<work-item-id>/triage" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-triage-key>" \
     -d '{"status":"ready","expected_touch":"<paths-or-surfaces>","acceptance":"<observable done condition>","validation":"<checks to run>","conflict_keys":["<stable-lock-key>"]}'
   ```

5. Query ready work for the registered project:

   ```bash
   curl "$KAIROTA_API_BASE_URL/queue/ready?repository_id=<repository-id>"
   ```

6. Claim work only through Kairota:

   ```bash
   curl -X POST "$KAIROTA_API_BASE_URL/queue/claim-next" \
     -H "Content-Type: application/json" \
     -H "Idempotency-Key: <stable-claim-key>" \
     -d '{"repository_id":"<repository-id>","owner":"<agent-or-worker-id>"}'
   ```

7. Before making external mutations, confirm the lease is still valid and keep
   progress recorded through worker-run reporting.

8. When done, report validation, PR, review, CI, and merge state back through the
   Kairota worker and repository sync surfaces. Do not close a work item based on
   local confidence alone when repository gates are still pending.

## Scheduler Interpretation

- `needs_triage`: the managed project's AI must add scheduling facts.
- `blocked`: dependency, human decision, repository gate, or failed validation
  prevents execution.
- `ready`: Kairota has enough facts and no blocking dependency or lock.
- `claimed` or `implementing`: another worker has lease authority.
- `waiting_checks`: implementation is waiting on repository or CI facts.
- `ci_failed` or `review_changes_requested`: repair work is needed before done.
- `done`: Kairota has recorded completion evidence.

## Boundaries

- Kairota does not decide issue dependencies by itself.
- Kairota does not replace GitHub, git, CI, or project-specific tests.
- Kairota does not grant permission to bypass the managed project's local
  instructions.
- If Kairota state conflicts with current repository facts, sync current facts
  first, then claim or triage.
