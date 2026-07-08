---
doc:
  updated_at: 2026-07-08
  category: architecture
  status: draft
  audience: ai
  keywords: [control-plane, architecture, product-scope]
  description: "Defines the planned Kairota control-plane architecture and boundaries."
---

# Control Plane Architecture

Status: draft. Product runtime code is not implemented yet.

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

- Backend framework.
- Frontend framework.
- Initial auth model.
- Exact database schema.
- Whether durable workflow execution needs Temporal or a smaller Postgres outbox first.
- Which GitHub-specific fields belong only in the first adapter.
