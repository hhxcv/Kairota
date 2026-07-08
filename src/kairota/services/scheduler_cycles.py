from __future__ import annotations

from datetime import timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    LeaseStatus,
    RiskLevel,
    SchedulerDecisionCode,
    WorkItemStatus,
)
from kairota.contracts.schemas import (
    ClaimNextWorkItemCommand,
    ClaimNextWorkItemRead,
    ClaimWorkItemCommand,
    ClaimWorkItemRead,
    LeaseExpiryRead,
    LeaseHeartbeatCommand,
    LeaseHeartbeatRead,
    SchedulerCycleCreate,
    SchedulerCycleRead,
    SchedulerDecisionRead,
)
from kairota.models.records import (
    Lease,
    LockHolder,
    Repository,
    SchedulerCycle,
    SchedulerDecision,
    SchedulerGuard,
    WorkItem,
    WorkItemConflictKey,
)
from kairota.scheduler.claims import (
    claim_work_item,
    expire_stale_leases,
    heartbeat_lease,
)
from kairota.scheduler.planner import (
    SchedulerPlanInput,
    WorkItemPlanInput,
    plan_scheduler_cycle,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command
from kairota.services.work_items import conflict_key_map, dependency_map


def run_scheduler_cycle_command(
    session: Session,
    *,
    command: SchedulerCycleCreate,
    idempotency_key: str,
) -> SchedulerCycleRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))

    def execute() -> JsonObject:
        validate_repository_scope(session, command.repository_id)
        ensure_scheduler_guard(session, command.queue_key)
        candidates = load_plan_candidates(session, repository_id=command.repository_id)
        completed_ids = load_completed_work_item_ids(session)
        active_conflicts = load_active_conflict_keys(session)
        plan = plan_scheduler_cycle(
            SchedulerPlanInput(
                candidates=candidates,
                completed_work_item_ids=completed_ids,
                active_conflict_keys=active_conflicts,
                capacity=command.capacity,
            )
        )

        cycle = SchedulerCycle(
            queue_key=command.queue_key,
            repository_id=command.repository_id,
            input_version="m1-api-cli-v1",
            result="planned",
            assigned_count=len(plan.assigned_work_item_ids),
            rejected_count=len(plan.decisions) - len(plan.assigned_work_item_ids),
        )
        session.add(cycle)
        session.flush()

        persisted_decisions: list[SchedulerDecision] = []
        for decision in plan.decisions:
            record = SchedulerDecision(
                cycle_id=cycle.id,
                work_item_id=decision.work_item_id,
                code=decision.code.value,
                explanation=decision.explanation,
                blocking_facts=decision.blocking_facts,
            )
            persisted_decisions.append(record)
        session.add_all(persisted_decisions)
        session.flush()

        read_model = scheduler_cycle_to_read(cycle, persisted_decisions)
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="scheduler.cycle",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return SchedulerCycleRead.model_validate(result.body)


def claim_next_work_item_command(
    session: Session,
    *,
    command: ClaimNextWorkItemCommand,
    idempotency_key: str,
) -> ClaimNextWorkItemRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))

    def execute() -> JsonObject:
        validate_repository_scope(session, command.repository_id)
        ensure_scheduler_guard(session, command.queue_key)
        candidates = load_plan_candidates(session, repository_id=command.repository_id)
        completed_ids = load_completed_work_item_ids(session)
        active_conflicts = load_active_conflict_keys(session)
        plan = plan_scheduler_cycle(
            SchedulerPlanInput(
                candidates=candidates,
                completed_work_item_ids=completed_ids,
                active_conflict_keys=active_conflicts,
                capacity=1,
            )
        )
        cycle = SchedulerCycle(
            queue_key=command.queue_key,
            repository_id=command.repository_id,
            input_version="m1-claim-next-v1",
            result="planned",
            assigned_count=len(plan.assigned_work_item_ids),
            rejected_count=len(plan.decisions) - len(plan.assigned_work_item_ids),
        )
        session.add(cycle)
        session.flush()
        session.add_all(
            SchedulerDecision(
                cycle_id=cycle.id,
                work_item_id=decision.work_item_id,
                code=decision.code.value,
                explanation=decision.explanation,
                blocking_facts=decision.blocking_facts,
            )
            for decision in plan.decisions
        )
        session.flush()
        if not plan.assigned_work_item_ids:
            first_decision = plan.decisions[0] if plan.decisions else None
            read_model = ClaimNextWorkItemRead(
                claimed=False,
                reason=first_decision.code if first_decision is not None else None,
                explanation=first_decision.explanation
                if first_decision is not None
                else "No schedulable work item was found.",
            )
            return cast(JsonObject, read_model.model_dump(mode="json"))

        work_item_id = plan.assigned_work_item_ids[0]
        stored_conflict_keys = frozenset(
            session.scalars(
                select(WorkItemConflictKey.conflict_key).where(
                    WorkItemConflictKey.work_item_id == work_item_id
                )
            )
        )
        claim = claim_work_item(
            session,
            work_item_id=work_item_id,
            owner=command.owner,
            conflict_keys=stored_conflict_keys,
            lease_ttl=timedelta(seconds=command.lease_ttl_seconds),
        )
        read_model = ClaimNextWorkItemRead(
            claimed=claim.claimed,
            work_item_id=claim.work_item_id,
            lease_id=claim.lease_id,
            fencing_token=claim.fencing_token,
            conflict_keys=claim.conflict_keys,
            reason=claim.reason,
            explanation=claim.explanation,
        )
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="queue.claim_next",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ClaimNextWorkItemRead.model_validate(result.body)


def claim_work_item_command(
    session: Session,
    *,
    work_item_id: str,
    command: ClaimWorkItemCommand,
    idempotency_key: str,
) -> ClaimWorkItemRead:
    payload: JsonObject = {
        "work_item_id": work_item_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        stored_conflict_keys = frozenset(
            session.scalars(
                select(WorkItemConflictKey.conflict_key).where(
                    WorkItemConflictKey.work_item_id == work_item_id
                )
            )
        )
        result = claim_work_item(
            session,
            work_item_id=work_item_id,
            owner=command.owner,
            conflict_keys=stored_conflict_keys,
            lease_ttl=timedelta(seconds=command.lease_ttl_seconds),
        )
        read_model = ClaimWorkItemRead(
            claimed=result.claimed,
            work_item_id=result.work_item_id,
            lease_id=result.lease_id,
            fencing_token=result.fencing_token,
            conflict_keys=result.conflict_keys,
            reason=result.reason,
            explanation=result.explanation,
        )
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="work_item.claim",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ClaimWorkItemRead.model_validate(result.body)


def heartbeat_lease_command(
    session: Session,
    *,
    lease_id: str,
    command: LeaseHeartbeatCommand,
    idempotency_key: str,
) -> LeaseHeartbeatRead:
    payload: JsonObject = {
        "lease_id": lease_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        result = heartbeat_lease(
            session,
            lease_id=lease_id,
            fencing_token=command.fencing_token,
            lease_ttl=timedelta(seconds=command.lease_ttl_seconds),
        )
        read_model = LeaseHeartbeatRead(
            refreshed=result.refreshed,
            lease_id=result.lease_id,
            explanation=result.explanation,
        )
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="lease.heartbeat",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return LeaseHeartbeatRead.model_validate(result.body)


def expire_stale_leases_command(
    session: Session,
    *,
    idempotency_key: str,
) -> LeaseExpiryRead:
    payload: JsonObject = {"scope": "stale_leases"}

    def execute() -> JsonObject:
        result = expire_stale_leases(session)
        read_model = LeaseExpiryRead(
            expired_lease_ids=result.expired_lease_ids,
            released_lock_ids=result.released_lock_ids,
        )
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="lease.expire_stale",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return LeaseExpiryRead.model_validate(result.body)


def scheduler_cycle_to_read(
    cycle: SchedulerCycle,
    decisions: list[SchedulerDecision],
) -> SchedulerCycleRead:
    return SchedulerCycleRead(
        id=cycle.id,
        queue_key=cycle.queue_key,
        repository_id=cycle.repository_id,
        result=cycle.result,
        assigned_count=cycle.assigned_count,
        rejected_count=cycle.rejected_count,
        decisions=tuple(
            SchedulerDecisionRead(
                id=decision.id,
                cycle_id=decision.cycle_id,
                work_item_id=decision.work_item_id,
                code=SchedulerDecisionCode(decision.code),
                explanation=decision.explanation,
                blocking_facts=decision.blocking_facts,
            )
            for decision in decisions
        ),
    )


def ensure_scheduler_guard(session: Session, queue_key: str) -> SchedulerGuard:
    guard = session.scalar(
        select(SchedulerGuard)
        .where(SchedulerGuard.queue_key == queue_key)
        .with_for_update()
    )
    if guard is None:
        guard = SchedulerGuard(queue_key=queue_key)
        session.add(guard)
        session.flush()
    return guard


def load_plan_candidates(
    session: Session,
    *,
    repository_id: str | None = None,
) -> tuple[WorkItemPlanInput, ...]:
    conflict_keys = conflict_key_map(session)
    dependencies = dependency_map(session)
    statement = select(WorkItem).order_by(
        WorkItem.priority,
        WorkItem.created_at,
        WorkItem.id,
    )
    if repository_id is not None:
        statement = statement.where(WorkItem.repository_id == repository_id)
    work_items = tuple(session.scalars(statement))
    return tuple(
        WorkItemPlanInput(
            id=work_item.id,
            status=WorkItemStatus(work_item.status),
            priority=work_item.priority,
            risk=RiskLevel(work_item.risk),
            created_order=index,
            expected_touch=work_item.expected_touch,
            acceptance=work_item.acceptance,
            validation=work_item.validation,
            conflict_keys=conflict_keys.get(work_item.id, frozenset()),
            dependency_ids=dependencies.get(work_item.id, frozenset()),
        )
        for index, work_item in enumerate(work_items)
    )


def load_completed_work_item_ids(session: Session) -> frozenset[str]:
    completed_statuses = (WorkItemStatus.MERGED.value, WorkItemStatus.DONE.value)
    return frozenset(
        session.scalars(
            select(WorkItem.id).where(WorkItem.status.in_(completed_statuses))
        )
    )


def load_active_conflict_keys(session: Session) -> frozenset[str]:
    active_lease_ids = select(Lease.id).where(Lease.status == LeaseStatus.ACTIVE.value)
    return frozenset(
        session.scalars(
            select(LockHolder.conflict_key).where(
                LockHolder.released_at.is_(None),
                (
                    LockHolder.lease_id.is_(None)
                    | LockHolder.lease_id.in_(active_lease_ids)
                ),
            )
        )
    )


def validate_repository_scope(session: Session, repository_id: str | None) -> None:
    if repository_id is None:
        return
    if session.get(Repository, repository_id) is None:
        raise CommandBlockedError(
            "repository_not_found",
            "Repository does not exist.",
            {"repository_id": repository_id},
        )
