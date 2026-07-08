from kairota.contracts.enums import RiskLevel, SchedulerDecisionCode, WorkItemStatus
from kairota.scheduler.planner import (
    FALLBACK_CONFLICT_KEY,
    SchedulerPlanInput,
    WorkItemPlanInput,
    plan_scheduler_cycle,
)


def candidate(
    item_id: str,
    *,
    status: WorkItemStatus = WorkItemStatus.READY,
    priority: int = 100,
    risk: RiskLevel = RiskLevel.MEDIUM,
    created_order: int = 0,
    expected_touch: str | None = "src/**",
    acceptance: str | None = "done criteria",
    validation: str | None = "pytest",
    conflict_keys: frozenset[str] = frozenset({"repo:kairota:path:src/**"}),
    dependency_ids: frozenset[str] = frozenset(),
) -> WorkItemPlanInput:
    return WorkItemPlanInput(
        id=item_id,
        status=status,
        priority=priority,
        risk=risk,
        created_order=created_order,
        expected_touch=expected_touch,
        acceptance=acceptance,
        validation=validation,
        conflict_keys=conflict_keys,
        dependency_ids=dependency_ids,
    )


def test_planner_assigns_by_priority_risk_creation_order() -> None:
    plan = plan_scheduler_cycle(
        SchedulerPlanInput(
            candidates=(
                candidate(
                    "high-risk",
                    priority=10,
                    risk=RiskLevel.HIGH,
                    created_order=1,
                    conflict_keys=frozenset({"repo:kairota:path:src/**"}),
                ),
                candidate(
                    "low-risk",
                    priority=10,
                    risk=RiskLevel.LOW,
                    created_order=2,
                    conflict_keys=frozenset({"repo:kairota:path:docs/**"}),
                ),
                candidate(
                    "higher-priority",
                    priority=1,
                    risk=RiskLevel.CRITICAL,
                    conflict_keys=frozenset({"repo:kairota:path:api/**"}),
                ),
            ),
            capacity=3,
        )
    )

    assert plan.assigned_work_item_ids == (
        "higher-priority",
        "low-risk",
        "high-risk",
    )


def test_planner_is_deterministic_for_same_inputs() -> None:
    plan_input = SchedulerPlanInput(
        candidates=(
            candidate("b", priority=10, created_order=2),
            candidate("a", priority=10, created_order=1),
        ),
        capacity=1,
    )

    assert plan_scheduler_cycle(plan_input) == plan_scheduler_cycle(plan_input)


def test_planner_blocks_missing_required_triage_facts() -> None:
    plan = plan_scheduler_cycle(
        SchedulerPlanInput(
            candidates=(
                candidate("touch", expected_touch=" ", created_order=1),
                candidate("acceptance", acceptance=None, created_order=2),
                candidate("validation", validation="", created_order=3),
            ),
            capacity=3,
        )
    )

    assert [decision.code for decision in plan.decisions] == [
        SchedulerDecisionCode.BLOCKED_BY_MISSING_EXPECTED_TOUCH,
        SchedulerDecisionCode.BLOCKED_BY_MISSING_ACCEPTANCE,
        SchedulerDecisionCode.BLOCKED_BY_MISSING_VALIDATION,
    ]


def test_planner_blocks_status_dependencies_capacity_and_conflicts() -> None:
    plan = plan_scheduler_cycle(
        SchedulerPlanInput(
            candidates=(
                candidate("status", status=WorkItemStatus.BACKLOG, created_order=1),
                candidate(
                    "dependency",
                    dependency_ids=frozenset({"root"}),
                    created_order=2,
                ),
                candidate(
                    "conflict",
                    conflict_keys=frozenset({"contract:scheduler"}),
                    created_order=3,
                ),
                candidate(
                    "capacity",
                    conflict_keys=frozenset({"repo:kairota:path:docs/**"}),
                    created_order=4,
                ),
            ),
            completed_work_item_ids=frozenset(),
            active_conflict_keys=frozenset({"contract:scheduler"}),
            capacity=0,
        )
    )

    assert [decision.code for decision in plan.decisions] == [
        SchedulerDecisionCode.BLOCKED_BY_STATUS,
        SchedulerDecisionCode.BLOCKED_BY_DEPENDENCY,
        SchedulerDecisionCode.BLOCKED_BY_CAPACITY,
        SchedulerDecisionCode.BLOCKED_BY_CAPACITY,
    ]


def test_planner_blocks_active_conflicts_when_capacity_exists() -> None:
    plan = plan_scheduler_cycle(
        SchedulerPlanInput(
            candidates=(
                candidate(
                    "conflict",
                    conflict_keys=frozenset({"contract:scheduler"}),
                ),
            ),
            active_conflict_keys=frozenset({"contract:scheduler"}),
            capacity=1,
        )
    )

    assert plan.decisions[0].code == SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY


def test_planner_uses_conservative_fallback_for_missing_conflict_keys() -> None:
    plan = plan_scheduler_cycle(
        SchedulerPlanInput(
            candidates=(
                candidate("first", conflict_keys=frozenset()),
                candidate("second", conflict_keys=frozenset()),
            ),
            capacity=2,
        )
    )

    assert plan.assigned_work_item_ids == ("first",)
    assert plan.decisions[0].conflict_keys == (FALLBACK_CONFLICT_KEY,)
    assert plan.decisions[1].code == SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY
