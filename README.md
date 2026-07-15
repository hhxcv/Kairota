# Kairota

Kairota is a local scheduling service for AI-developed GitHub projects. It keeps
GitHub Issue facts synchronized, stores dependency analysis supplied by each
project's main AI, computes ready work, and gives humans one UI for project
progress.

Kairota is deliberately mechanical. It does not analyze Issue meaning, run
subagents, enforce a worker cap, or use PR, CI, review, lease, attempt, or worker
state for scheduling. The managed project's single main AI owns those concerns.

## Scheduling Model

Every synced Issue has one of five states:

| State | Meaning |
| --- | --- |
| `needs_analysis` | The main AI must submit the Issue's dependency analysis. |
| `blocked` | At least one dependency Issue is open, or analysis has a manual hold. |
| `ready` | Analysis is complete and every dependency Issue is closed. |
| `in_progress` | The main AI atomically claimed the Issue and assigned its work. |
| `closed` | GitHub reports the Issue closed; downstream dependencies are satisfied. |

`ready -> in_progress` is the only claim transition. GitHub close produces
`closed`. Reopening or releasing an Issue invalidates its old dependency
analysis and returns it to `needs_analysis`.

## Install And Run

Requirements: Python 3.11+ and Node.js for the web UI.

```bash
python -m pip install -e ".[dev]"
kairota serve
```

Kairota listens at `http://127.0.0.1:8010`. It creates and upgrades its internal
SQLite database automatically. Normal users do not configure a database URL or
run migrations.

In a second terminal:

```bash
cd web
npm install
npm run dev
```

The web app uses the fixed local API URL without Vite configuration. Add the
first project from the UI or with:

```bash
kairota projects register <github-owner>/<github-repo>
```

`KAIROTA_GITHUB_TOKEN` is optional for public repositories and needed for private
repositories or higher API limits. `KAIROTA_GITHUB_WEBHOOK_SECRET` is optional;
polling remains the repair and convergence path.

## Use From Another Project

1. Start Kairota and its web UI.
2. Add the GitHub project in Kairota. The service immediately owns sync and
   scheduling records for that project.
3. Install `skills/kairota-managed-project/` into the managed project's AI skill
   location.
4. Tell that project's main AI: "Use the Kairota managed-project skill and
   complete this repository's Issues."

The main AI then performs this loop:

1. Find the registered project and refresh GitHub facts.
2. Reconcile every `in_progress` Issue with the subagents it currently owns.
3. If any open Issue is `needs_analysis`, analyze the graph and submit dependency
   Issue numbers before dispatching new work.
4. Query claimable `ready` Issues, apply its own worker cap, atomically claim the
   selected Issues, and assign subagents.
5. Validate completed work and close the corresponding GitHub Issue. Kairota's
   webhook or polling sync moves it to `closed` and may unlock dependents.
6. Release an `in_progress` Issue when the main AI can no longer confirm active
   ownership; it must be analyzed again before another claim.

Subagents never call Kairota directly.

## REST Examples

Register and sync a project:

```bash
curl -X POST "http://127.0.0.1:8010/projects" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: register-owner-repo" \
  -d '{"remote":"<github-owner>/<github-repo>"}'

curl -X POST "http://127.0.0.1:8010/projects/<project-id>/sync" \
  -H "Idempotency-Key: sync-owner-repo-1"
```

Analyze and claim an Issue:

```bash
curl -X PUT "http://127.0.0.1:8010/issues/<issue-id>/analysis" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: analyze-<issue-id>-v0" \
  -d '{"expected_analysis_version":0,"dependency_issue_numbers":[12,18]}'

curl "http://127.0.0.1:8010/issues?project_id=<project-id>&state=ready&claimable=true"

curl -X POST "http://127.0.0.1:8010/issues/<issue-id>/claim" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: claim-<issue-id>-v1" \
  -d '{"expected_scheduling_version":1}'
```

Every write requires an `Idempotency-Key`. Reuse the same key only when retrying
the same logical command with the same body. On a version conflict, re-read the
Issue before deciding again.

## Validation

```bash
pytest -q
ruff check src tests migrations
mypy src
python .agents/checks/check_ai_governance.py
git diff --check

cd web
npm test
npm run build
```

Start with `docs/README.md` for durable architecture, contracts, and validation
evidence. Installable project guidance lives in `skills/`; Kairota's identical
dogfood copy lives in `.agents/skills/`.
