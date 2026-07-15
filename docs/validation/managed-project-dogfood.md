---
doc:
  updated_at: 2026-07-10
  category: validation
  status: current
  audience: ai
  keywords: [dogfood, managed-project, dependency-graph]
  description: "Records the current complex managed Issue validation design."
---

# Managed Project Dogfood

## Scenario

The automated complex case contains 24 Issues in four layers:

- Issues 1-4 are independent roots.
- Issues 5-12 fan out across one or two roots.
- Issues 13-20 combine second-layer work.
- Issues 21-23 fan in, and Issue 24 is the final fan-in.

The test's main-AI harness owns a worker cap of four. It queries all ready Issues,
claims at most four, simulates validated completion by closing those GitHub Issue
facts, synchronizes them, and repeats until all 24 are closed. Kairota never
stores or enforces that cap.

## Invariants Observed By Automation

- New open Issues start in `needs_analysis`.
- Analyzed roots become ready in parallel; dependent Issues remain blocked.
- Closing roots unlocks only Issues whose complete dependency set is closed.
- At least one dispatch wave contains four Issues.
- All 24 Issues eventually reach `closed` without duplicate dispatch.
- Reopen invalidates the reopened Issue's analysis and re-blocks dependents.
- Release invalidates active work and requires fresh analysis.
- Sync error or staleness preserves visibility but prevents claim.
- Project filters and dependency lookup remain project-local.

## Runtime Evidence

Kairota was registered as its own real GitHub project after the destructive
database reset. The first synchronization read 201 real Issues with no product
fixtures. The live complex run reused temporary Issues #188-#211:

- Reopening all 24 produced exactly 24 `needs_analysis` rows.
- Submitting the graph produced 4 ready roots and 20 blocked dependents.
- The main AI claimed four roots and assigned four parallel subagents. Each
  subagent read its Issue and reported completion only to the main AI.
- Closing the roots produced eight ready second-layer Issues.
- #195 simulated subagent startup failure: release returned `needs_analysis`,
  fresh analysis returned `ready`, and a new versioned claim succeeded.
- #188 was closed and immediately reopened between polls. Polling correctly saw
  only the final open fact, so the main AI reconciled the ended worker, released
  the Issue, analyzed it again, and reclaimed it. This confirms polling cannot
  reconstruct an unobserved intermediate state and the documented recovery path
  is necessary.
- Later real claim waves were #196-#199, #200-#203, #204-#207, #208-#210, and
  #211. The final manual hold was cleared only after all three dependencies were
  closed.
- The run ended with all 24 GitHub Issues and all 24 Kairota projections closed.

Playwright observed the real service at 1440x900 and 390x844 during the run. The
intermediate UI showed exactly 12 blocked, 4 ready, 4 in progress, and 4 closed;
the final UI showed 24 closed. Project multi-select, manual synchronization,
state filtering, Issue details, dependencies, add-project validation, and mobile
layout matched API facts with no console errors or horizontal overflow.

The live pass found and fixed three user-visible defects:

- SQLite datetimes lost UTC information and appeared several hours stale in the
  browser; JSON contracts now serialize UTC with `Z`.
- Mobile details were rendered after the entire Issue list; they now open as an
  immediately visible fixed drawer.
- Project registration required a second manual synchronization; the UI now
  synchronizes the new project immediately.
