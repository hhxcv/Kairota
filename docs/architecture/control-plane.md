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

Status: mixed current and planned. M1 runtime foundation has started; scheduler,
worker runtime, GitHub sync, and queue data flows are not implemented yet.

## Purpose

Kairota is a personal AI work control plane. The first product slice replaces
GitHub Project as the durable scheduler for autonomous development work. GitHub
is the first adapter, not the core architecture boundary.

## Planned Layers

| Layer | Owns |
| --- | --- |
| Control Kernel | Work items, dependencies, claims, leases, conflict locks, worker runs, events |
| Integration Adapters | Repository providers, AI runtimes, CI, local repos, future external tools |
| Interfaces | Web UI, CLI, REST API, MCP server, webhook receiver |
| Observability | Cost events, duration, retries, review cycle, worker utilization |
| Experience Hub | Cross-project patterns, anti-patterns, postmortems, adoption records |

## Architecture Decisions

- Kairota-owned contracts are scheduler truth; external systems are caches or sources.
- Postgres is the expected store for claim, lease, and lock safety.
- Integration adapters convert external state into Kairota records.
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

- M1 initial runtime, scheduler, adapter, and UI choices are drafted in
  `docs/architecture/m1-ai-dev-queue.md`.
- Initial auth model beyond single-operator local mode.
- Exact database schema as implemented migrations.
- Threshold for introducing Temporal or another durable workflow engine after M1.
- Which GitHub-specific fields need long-term adapter-only retention after the
  first adapter is implemented.
