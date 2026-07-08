---
doc:
  updated_at: 2026-07-08
  category: contract
  status: draft
  audience: ai
  keywords: [experience, pattern, postmortem, adoption]
  description: "Defines planned cross-project experience records."
---

# Experience Registry

Status: draft. No registry is implemented yet.

## Planned Role

The experience registry lets projects share reusable AI development practices
without copying noisy local history.

## Record Types

- Pattern.
- Anti-pattern.
- Skill template.
- Governance rule.
- Validation rule.
- Postmortem.
- Adoption record.

## Adoption Flow

1. Source project publishes a concise experience record.
2. Kairota indexes owner, trigger, benefit, risk, and evidence.
3. Target project evaluates applicability.
4. Target project adapts locally through a normal PR or change process.
5. Adoption result feeds back into the experience record.

## Consultant Agent Boundary

Consultant-style agents may review and advise other projects. They should not
mutate target repos unless explicitly authorized by that project.
