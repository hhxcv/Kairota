# Kairota

Kairota is a planned personal AI work control plane.

The first product slice replaces GitHub Project as the durable scheduler for
AI-assisted development. GitHub is the first adapter, not the architecture
boundary. Kairota will own work items, dependencies, claims, leases, conflict
locks, worker runs, repository check summaries, and a compact UI that shows what
is ready, blocked, running, waiting, or done.

Future slices may add cost monitoring, project-management surfaces, cross-project
experience sharing, and consultant-style agents.

## Status

Repository incubation is in progress. Product runtime code is not implemented
yet. Current files establish AI development rules, docs routing, initial skills,
and planned product contracts.

## Current Commands

```bash
python .agents/checks/check_ai_governance.py
git diff --check
```

Product build, test, and run commands are not established yet.

## Docs

Start with `docs/README.md`.

Durable project facts live in `docs/`. AI workflows live in `.agents/skills/`.
Root invariants live in `AGENTS.md`.
