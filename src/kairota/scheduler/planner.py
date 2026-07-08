from __future__ import annotations

from dataclasses import dataclass, field

from kairota.contracts.enums import RiskLevel, SchedulerDecisionCode, WorkItemStatus

RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

FALLBACK_CONFLICT_KEY = "unknown:conservative"


@dataclass(frozen=True)
class WorkItemPlanInput:
    id: str
    status: WorkItemStatus
    priority: int
    risk: RiskLevel
    created_order: int
    expected_touch: str | None
    acceptance: str | None
    validation: str | None
    conflict_keys: frozenset[str] = field(default_factory=frozenset)
    dependency_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SchedulerPlanInput:
    candidates: tuple[WorkItemPlanInput, ...]
    completed_work_item_ids: frozenset[str] = field(default_factory=frozenset)
    active_conflict_keys: frozenset[str] = field(default_factory=frozenset)
    capacity: int = 1


@dataclass(frozen=True)
class SchedulerPlanDecision:
    work_item_id: str
    code: SchedulerDecisionCode
    explanation: str
    conflict_keys: tuple[str, ...] = ()
    blocking_facts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SchedulerPlan:
    decisions: tuple[SchedulerPlanDecision, ...]
    assigned_work_item_ids: tuple[str, ...]
    active_conflict_keys: frozenset[str]


def plan_scheduler_cycle(plan_input: SchedulerPlanInput) -> SchedulerPlan:
    assigned_ids: list[str] = []
    decisions: list[SchedulerPlanDecision] = []
    claimed_conflicts = set(plan_input.active_conflict_keys)
    capacity = max(plan_input.capacity, 0)

    for item in sorted(plan_input.candidates, key=sort_key):
        decision = evaluate_candidate(
            item=item,
            completed_work_item_ids=plan_input.completed_work_item_ids,
            active_conflict_keys=frozenset(claimed_conflicts),
            remaining_capacity=capacity - len(assigned_ids),
        )
        decisions.append(decision)
        if decision.code == SchedulerDecisionCode.ASSIGNED:
            assigned_ids.append(item.id)
            claimed_conflicts.update(decision.conflict_keys)

    return SchedulerPlan(
        decisions=tuple(decisions),
        assigned_work_item_ids=tuple(assigned_ids),
        active_conflict_keys=frozenset(claimed_conflicts),
    )


def sort_key(item: WorkItemPlanInput) -> tuple[int, int, int, str]:
    return (item.priority, RISK_ORDER[item.risk], item.created_order, item.id)


def evaluate_candidate(
    item: WorkItemPlanInput,
    completed_work_item_ids: frozenset[str],
    active_conflict_keys: frozenset[str],
    remaining_capacity: int,
) -> SchedulerPlanDecision:
    if item.status != WorkItemStatus.READY:
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_STATUS,
            "Work item is not ready.",
            {"status": item.status.value},
        )

    missing_dependencies = sorted(item.dependency_ids - completed_work_item_ids)
    if missing_dependencies:
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_DEPENDENCY,
            "Work item has unfinished dependencies.",
            {"missing_dependencies": missing_dependencies},
        )

    if not present(item.expected_touch):
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_MISSING_EXPECTED_TOUCH,
            "Work item is missing expected touch facts.",
        )

    if not present(item.acceptance):
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_MISSING_ACCEPTANCE,
            "Work item is missing acceptance criteria.",
        )

    if not present(item.validation):
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_MISSING_VALIDATION,
            "Work item is missing validation evidence requirements.",
        )

    if remaining_capacity <= 0:
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_CAPACITY,
            "No worker capacity remains.",
        )

    conflict_keys = normalized_conflict_keys(item)
    conflicts = sorted(set(conflict_keys) & active_conflict_keys)
    if conflicts:
        return blocked(
            item,
            SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY,
            "Work item conflicts with active work.",
            {"conflict_keys": conflicts},
        )

    return SchedulerPlanDecision(
        work_item_id=item.id,
        code=SchedulerDecisionCode.ASSIGNED,
        explanation="Work item is eligible for assignment.",
        conflict_keys=conflict_keys,
    )


def blocked(
    item: WorkItemPlanInput,
    code: SchedulerDecisionCode,
    explanation: str,
    blocking_facts: dict[str, object] | None = None,
) -> SchedulerPlanDecision:
    return SchedulerPlanDecision(
        work_item_id=item.id,
        code=code,
        explanation=explanation,
        blocking_facts=blocking_facts or {},
    )


def normalized_conflict_keys(item: WorkItemPlanInput) -> tuple[str, ...]:
    if item.conflict_keys:
        return tuple(sorted(item.conflict_keys))
    return (FALLBACK_CONFLICT_KEY,)


def present(value: str | None) -> bool:
    return bool(value and value.strip())
