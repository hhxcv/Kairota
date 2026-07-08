---
doc:
  updated_at: 2026-07-08
  category: index
  status: current
  audience: ai
  keywords: [docs-index, routing, owner-docs]
  description: "Routes AI readers to Kairota owner docs without repeating facts."
---

# Docs Index

Open the smallest owner doc that matches the task. Do not use this index as a
fact source.

| Task | Keywords | Open | Do not open by default |
| --- | --- | --- | --- |
| Understand product scope and system shape | architecture, control-plane, scope | `docs/architecture/control-plane.md` | Contract details |
| Plan or implement M1 AI Dev Queue | m1, ai-dev-queue, scheduler, implementation-plan | `docs/architecture/m1-ai-dev-queue.md` | Cost or experience docs |
| Design or review the first UI | ui, dashboard, workbench, design | `docs/design/product-ui.md` | Backend contracts |
| Define or inspect work item facts | work-item, issue, task, status | `docs/contracts/work-items.md` | Scheduler internals |
| Define or inspect scheduler behavior | scheduler, lease, claim, lock | `docs/contracts/scheduler.md` | UI design |
| Define or inspect worker run facts | worker, agent, run, lifecycle | `docs/contracts/agent-runs.md` | Cost charts |
| Define or inspect cost data | token, cost, duration, metrics | `docs/contracts/cost-events.md` | Work item details |
| Define or inspect reusable experience facts | pattern, postmortem, adoption | `docs/contracts/experience-registry.md` | Scheduler details |
| Design integration APIs | api, mcp, webhook, adapter | `docs/interfaces/control-api.md` | UI details |
| Check privacy and public text rules | privacy, secrets, local-info | `docs/governance/privacy.md` | Product contracts |
| Choose validation for current repo state | validation, checks, baseline | `docs/validation/baseline.md` | Product roadmap |
