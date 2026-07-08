---
doc:
  updated_at: 2026-07-08
  category: architecture
  status: mixed-current-planned
  audience: ai
  keywords: [control-plane, architecture, product-scope]
  description: "Defines the planned Kairota control-plane architecture and boundaries."
---

# Control Plane Architecture

Status: mixed current and planned. M1 runtime foundation, scheduler, claim and
lease services, GitHub sync, repository registration, API/CLI boundaries, queue
workbench UI, root managed-project skill, and worker run lifecycle commands are
implemented. MCP, broad observability, and experience hub capabilities remain
planned.

## Purpose

Kairota is a personal AI work control plane. The first product slice replaces
GitHub Project as the durable scheduler for autonomous development work. GitHub
is the first adapter, not the core architecture boundary.

Kairota runs as a local service. Other projects configure the Kairota service
address, register their GitHub repository, and then let Kairota monitor issue
state and identify ready work. The managed project's AI uses the installable
skill in `skills/kairota-managed-project` to analyze issue dependencies and
conflicts, submit triage facts, claim ready work, and report worker progress.
Humans use the web UI to understand progress and blockers.

## Planned Layers

| Layer | Owns |
| --- | --- |
| Control Kernel | Work items, dependencies, claims, leases, conflict locks, worker runs, events |
| Integration Adapters | Repository providers, AI runtimes, CI, local repos, future external tools |
| Interfaces | Web UI, CLI, REST API, installable skills, MCP server, webhook receiver |
| Observability | Cost events, duration, retries, review cycle, worker utilization |
| Experience Hub | Cross-project patterns, anti-patterns, postmortems, adoption records |

## Architecture Decisions

- Kairota-owned contracts are scheduler truth; external systems are caches or sources.
- Postgres is the expected store for claim, lease, and lock safety.
- Integration adapters convert external state into Kairota records.
- Kairota is the mechanical scheduler; project-local AI owns semantic issue
  analysis, dependency definition, and conflict-key selection.
- Root `skills/` is the distribution surface for managed projects; matching
  dogfood copies in `.agents/skills/` keep Kairota itself on the same workflow.
- The first UI must show queue health before it adds general project-management features.
- Cost and experience features should reuse the same event and work item model.

## Non-Goals

- Full document editor.
- Generic chat product.
- Hosted multi-tenant SaaS.
- Source-code hosting.
- CI execution.
- Secret manager.
- Remote-control automation without explicit adapters and audit.

## Open Decisions

- Initial auth model beyond single-operator local mode.
- Threshold for introducing Temporal or another durable workflow engine after M1.
- Which GitHub-specific fields need long-term adapter-only retention after the
  first adapter is implemented.
