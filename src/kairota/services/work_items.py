from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kairota.contracts.enums import LeaseStatus, WorkItemStatus
from kairota.contracts.schemas import QueueSummaryRead, WorkItemCreate, WorkItemRead
from kairota.models.records import (
    AuditEvent,
    Lease,
    LockHolder,
    WorkItem,
    WorkItemConflictKey,
    WorkItemDependency,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command

ALLOWED_CREATE_STATUSES = frozenset(
    {
        WorkItemStatus.NEEDS_TRIAGE.value,
        WorkItemStatus.BACKLOG.value,
        WorkItemStatus.READY.value,
        WorkItemStatus.BLOCKED.value,
        WorkItemStatus.HUMAN_DECISION.value,
    }
)


def create_work_item_command(
    session: Session,
    *,
    command: WorkItemCreate,
    idempotency_key: str,
    actor: str = "local",
) -> WorkItemRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))
    validate_create_command(session, command)

    def execute() -> JsonObject:
        work_item = WorkItem(
            title=command.title,
            status=str(command.status),
            priority=command.priority,
            risk=str(command.risk),
            work_type=str(command.work_type),
            autonomy_mode=str(command.autonomy_mode),
            acceptance=command.acceptance,
            validation=command.validation,
            expected_touch=command.expected_touch,
            source_url=command.source_url,
        )
        session.add(work_item)
        session.flush()

        add_conflict_keys(session, work_item.id, command.conflict_keys)
        add_dependencies(session, work_item.id, command.dependency_ids)
        session.add(
            AuditEvent(
                actor=actor,
                action="create_work_item",
                subject_type="work_item",
                subject_id=work_item.id,
                summary="Work item created through a bounded command.",
                details={"status": str(command.status)},
            )
        )
        session.flush()
        return cast(
            JsonObject, work_item_to_read(session, work_item).model_dump(mode="json")
        )

    result = run_idempotent_command(
        session,
        command_name="work_item.create",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkItemRead.model_validate(result.body)


def list_work_items(
    session: Session,
    *,
    status: WorkItemStatus | None = None,
) -> tuple[WorkItemRead, ...]:
    statement = select(WorkItem).order_by(
        WorkItem.priority,
        WorkItem.created_at,
        WorkItem.id,
    )
    if status is not None:
        statement = statement.where(WorkItem.status == status.value)
    return tuple(
        work_item_to_read(session, item) for item in session.scalars(statement)
    )


def get_work_item(session: Session, work_item_id: str) -> WorkItemRead | None:
    work_item = session.get(WorkItem, work_item_id)
    if work_item is None:
        return None
    return work_item_to_read(session, work_item)


def queue_summary(session: Session) -> QueueSummaryRead:
    status_counts: Counter[str] = Counter()
    for status, count in session.execute(
        select(WorkItem.status, func.count(WorkItem.id)).group_by(WorkItem.status)
    ):
        status_counts[str(status)] = int(count)
    active_leases = session.scalar(
        select(func.count(Lease.id)).where(Lease.status == LeaseStatus.ACTIVE.value)
    )
    active_locks = session.scalar(
        select(func.count(LockHolder.id)).where(LockHolder.released_at.is_(None))
    )
    total = sum(status_counts.values())
    return QueueSummaryRead(
        total=total,
        by_status={
            status.value: status_counts.get(status.value, 0)
            for status in WorkItemStatus
        },
        active_leases=int(active_leases or 0),
        active_locks=int(active_locks or 0),
    )


def work_item_to_read(session: Session, work_item: WorkItem) -> WorkItemRead:
    conflict_keys = tuple(
        session.scalars(
            select(WorkItemConflictKey.conflict_key)
            .where(WorkItemConflictKey.work_item_id == work_item.id)
            .order_by(WorkItemConflictKey.conflict_key)
        )
    )
    dependency_ids = tuple(
        session.scalars(
            select(WorkItemDependency.depends_on_work_item_id)
            .where(WorkItemDependency.work_item_id == work_item.id)
            .order_by(WorkItemDependency.depends_on_work_item_id)
        )
    )
    return WorkItemRead(
        id=work_item.id,
        title=work_item.title,
        status=WorkItemStatus(work_item.status),
        priority=work_item.priority,
        risk=work_item.risk,
        work_type=work_item.work_type,
        autonomy_mode=work_item.autonomy_mode,
        acceptance=work_item.acceptance,
        validation=work_item.validation,
        expected_touch=work_item.expected_touch,
        source_url=work_item.source_url,
        conflict_keys=conflict_keys,
        dependency_ids=dependency_ids,
        created_at=work_item.created_at,
        updated_at=work_item.updated_at,
    )


def validate_create_command(session: Session, command: WorkItemCreate) -> None:
    status = str(command.status)
    if status not in ALLOWED_CREATE_STATUSES:
        raise CommandBlockedError(
            "invalid_initial_status",
            "Work item create can only use a safe initial status.",
            {"status": status},
        )

    requested_dependency_ids = {
        dependency_id.strip()
        for dependency_id in command.dependency_ids
        if dependency_id.strip()
    }
    if not requested_dependency_ids:
        return

    existing_dependency_ids = set(
        session.scalars(
            select(WorkItem.id).where(WorkItem.id.in_(requested_dependency_ids))
        )
    )
    missing_dependency_ids = tuple(
        sorted(requested_dependency_ids - existing_dependency_ids)
    )
    if missing_dependency_ids:
        raise CommandBlockedError(
            "missing_dependency",
            "Work item create references dependencies that do not exist.",
            {"dependency_ids": missing_dependency_ids},
        )


def add_conflict_keys(
    session: Session,
    work_item_id: str,
    conflict_keys: Iterable[str],
) -> None:
    unique_keys = tuple(sorted({key.strip() for key in conflict_keys if key.strip()}))
    session.add_all(
        WorkItemConflictKey(work_item_id=work_item_id, conflict_key=key)
        for key in unique_keys
    )


def add_dependencies(
    session: Session,
    work_item_id: str,
    dependency_ids: Iterable[str],
) -> None:
    unique_dependency_ids = tuple(
        sorted(
            {
                dependency_id.strip()
                for dependency_id in dependency_ids
                if dependency_id.strip()
            }
        )
    )
    session.add_all(
        WorkItemDependency(
            work_item_id=work_item_id,
            depends_on_work_item_id=dependency_id,
        )
        for dependency_id in unique_dependency_ids
    )


def conflict_key_map(session: Session) -> dict[str, frozenset[str]]:
    grouped: defaultdict[str, set[str]] = defaultdict(set)
    for work_item_id, conflict_key in session.execute(
        select(WorkItemConflictKey.work_item_id, WorkItemConflictKey.conflict_key)
    ):
        grouped[str(work_item_id)].add(str(conflict_key))
    return {work_item_id: frozenset(keys) for work_item_id, keys in grouped.items()}


def dependency_map(session: Session) -> dict[str, frozenset[str]]:
    grouped: defaultdict[str, set[str]] = defaultdict(set)
    for work_item_id, dependency_id in session.execute(
        select(
            WorkItemDependency.work_item_id,
            WorkItemDependency.depends_on_work_item_id,
        )
    ):
        grouped[str(work_item_id)].add(str(dependency_id))
    return {work_item_id: frozenset(ids) for work_item_id, ids in grouped.items()}
