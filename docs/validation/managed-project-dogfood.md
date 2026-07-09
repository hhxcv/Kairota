---
doc:
  updated_at: 2026-07-09
  category: validation
  status: current
  audience: ai
  keywords: [validation, dogfood, managed-project, scheduler, github]
  description: "Records managed-project dogfood validation coverage and observations."
---

# Managed Project Dogfood Validation

## Purpose

Kairota must work as a local control plane for other repositories, not as a
single-project demo. Validation therefore needs to cover repository registration,
GitHub issue sync, managed-project AI triage facts, scheduler decisions,
capacity-limited claiming, worker-run reporting, and workbench visibility.

## Current Automated Coverage

`tests/test_managed_project_dogfood.py` covers the smallest managed-project loop:
register, sync one issue, triage, plan, claim, create a worker run, report, close
blocked, and read the scoped workbench.

`tests/test_managed_project_complex_scheduling.py` covers a 24 issue graph
through the GitHub sync boundary. It verifies:

- four parallel worker claims under `max_active_leases=4`;
- a fifth claim rejected with `blocked_by_capacity`;
- dependency blocking across multiple upstream issues;
- conflict-key blocking, including fallback conflict keys;
- expected touch, acceptance, and validation as metadata-only fields;
- backlog, blocked, and human-decision statuses;
- worker-run reporting, blocked close, lease release, and replacement claim.

`tests/test_api.py::test_claim_next_enforces_repository_worker_cap` and the CLI
smoke test cover the capacity contract at the API and local command surfaces.

## Live GitHub Observations

A live dogfood attempt using temporary GitHub issues found these issues:

- A hand-written validation script passed malformed triage arguments. This made
  the evidence unreliable and showed that live checks need a repeatable harness.
- A legacy native review poller made repository sync depend on an
  integration surface that Kairota does not need for the current comment-based
  review workflow.
- Immediately created GitHub issues may not appear in a following repository
  list response on the first sync attempt. Live validation must retry sync and
  observation before treating a missing temporary issue as a product failure.

The native review poller has been removed. The GitHub adapter uses REST
repository, issue, pull request, check, status, and issue-comment surfaces for
the current milestone. The live validation path is:

```bash
python .agents/checks/live_github_dogfood.py --repo <github-owner>/<github-repo>
```

The script creates 24 temporary issues, syncs until all are observed or the retry
budget is exhausted, runs the complex scheduling scenario against an isolated
database, and closes the temporary issues in cleanup.

## 2026-07-08 UTC Repeated Live E2E

Two live rounds were run with 24 temporary GitHub issues per round. Each round
covered:

- registration and repository sync into a fresh local database;
- four initial parallel worker claims with `max_active_leases=4`;
- a fifth claim rejected with `blocked_by_capacity`;
- dependency blocking before upstream issue close;
- GitHub issue close syncing work items to `done`;
- replacement claims after lease release;
- dependency unlock where C02 became ready only after A02 and B01 were closed;
- blocked, backlog, human-decision, missing-metadata, conflict-key, and fallback
  conflict-key cases;
- workbench rendering checked through a browser.

Round 1 passed scheduler validation and exposed UI/runtime issues:

- the web app could not read the API across local dev origins because the API did
  not emit CORS headers;
- search-filtered UI counts were inconsistent across the header, side
  navigation, board sections, and Decision Inbox;
- dependency details showed raw work item IDs, which made dependency state hard
  to verify from the UI.

Fixes applied:

- configurable local-origin CORS support in the API;
- unified search filtering for header visible count, navigation counts, board
  section counts, summary visible count, and Decision Inbox;
- dependency details resolve known dependency IDs to work item title and status.

Round 2 created a fresh 24-issue scenario and passed without new findings.
Filtered UI observation showed 24 visible work items: 14 ready, 4 running, 3
blocked, 0 waiting, 0 failed, and 3 done. The selected C02 item showed
`ready_for_claim` and displayed A02 and B01 dependencies as `done`. Browser
console checks showed no fetch or rendering errors.

## 2026-07-09 External Repository Migration Findings

A separate managed-project migration test against an active repository found
adoption blockers that are now covered by product changes and tests:

- Initial onboarding can use bounded `mode=issues` sync with issue filters, so
  large repositories do not need full PR/check enrichment before scheduling.
- Worker-run close with result `done` can complete non-PR work under the active
  lease and fencing token.
- CLI `work-items create --status` advertises only safe initial statuses.
- The web workbench displays the actual API base, service health, opaque
  database identity, and latest refresh state.
- Ready-status work with unmet dependencies or active conflict locks appears
  with blocker-specific actions instead of looking claimable.
- `claim-next` blocked responses include prioritized aggregate blocker counts.
- Triage updates are patch-like, so omitted scheduling facts are preserved.

## Remaining Gaps

Webhook delivery from GitHub can be unit-tested with signed payloads, but true
public webhook delivery still requires an externally reachable endpoint. Treat
that as an environment validation, not as a local unit test.
