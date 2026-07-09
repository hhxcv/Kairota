from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kairota.contracts.enums import LeaseStatus, WorkItemStatus
from kairota.contracts.schemas import (
    QueueSummaryRead,
    WorkItemCreate,
    WorkItemRead,
    WorkItemTriageCommand,
)
from kairota.models.records import (
    AuditEvent,
    Lease,
    LockHolder,
    Repository,
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
ALLOWED_TRIAGE_STATUSES = frozenset(
    {
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
            repository_id=command.repository_id,
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
    repository_id: str | None = None,
) -> tuple[WorkItemRead, ...]:
    statement = select(WorkItem).order_by(
        WorkItem.priority,
        WorkItem.created_at,
        WorkItem.id,
    )
    if status is not None:
        statement = statement.where(WorkItem.status == status.value)
    if repository_id is not None:
        statement = statement.where(WorkItem.repository_id == repository_id)
    return tuple(
        work_item_to_read(session, item) for item in session.scalars(statement)
    )


def get_work_item(session: Session, work_item_id: str) -> WorkItemRead | None:
    work_item = session.get(WorkItem, work_item_id)
    if work_item is None:
        return None
    return work_item_to_read(session, work_item)


def queue_summary(
    session: Session,
    *,
    repository_id: str | None = None,
) -> QueueSummaryRead:
    status_counts: Counter[str] = Counter()
    status_statement = select(WorkItem.status, func.count(WorkItem.id)).group_by(
        WorkItem.status
    )
    if repository_id is not None:
        status_statement = status_statement.where(
            WorkItem.repository_id == repository_id
        )
    for status, count in session.execute(status_statement):
        status_counts[str(status)] = int(count)
    active_leases_statement = select(func.count(Lease.id)).where(
        Lease.status == LeaseStatus.ACTIVE.value
    )
    active_locks_statement = select(func.count(LockHolder.id)).where(
        LockHolder.released_at.is_(None)
    )
    if repository_id is not None:
        active_leases_statement = active_leases_statement.join(
            WorkItem, Lease.work_item_id == WorkItem.id
        ).where(WorkItem.repository_id == repository_id)
        active_locks_statement = (
            active_locks_statement.join(Lease, LockHolder.lease_id == Lease.id)
            .join(WorkItem, Lease.work_item_id == WorkItem.id)
            .where(WorkItem.repository_id == repository_id)
        )
    active_leases = session.scalar(active_leases_statement)
    active_locks = session.scalar(active_locks_statement)
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
        repository_id=work_item.repository_id,
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
    validate_repository_exists(session, command.repository_id)
    requested_dependency_ids = {
        dependency_id.strip()
        for dependency_id in command.dependency_ids
        if dependency_id.strip()
    }
    validate_dependency_ids(session, requested_dependency_ids)


def triage_work_item_command(
    session: Session,
    *,
    work_item_id: str,
    command: WorkItemTriageCommand,
    idempotency_key: str,
    actor: str = "local",
) -> WorkItemRead:
    payload: JsonObject = {
        "work_item_id": work_item_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }
    validate_triage_command(session, work_item_id, command)

    def execute() -> JsonObject:
        work_item = session.get(WorkItem, work_item_id)
        if work_item is None:
            raise CommandBlockedError(
                "work_item_not_found",
                "Work item does not exist.",
                {"work_item_id": work_item_id},
            )
        if command.status is not None:
            work_item.status = str(command.status)
        if command.priority is not None:
            work_item.priority = command.priority
        if command.risk is not None:
            work_item.risk = str(command.risk)
        if command.work_type is not None:
            work_item.work_type = str(command.work_type)
        if command.autonomy_mode is not None:
            work_item.autonomy_mode = str(command.autonomy_mode)
        if command.expected_touch is not None:
            work_item.expected_touch = command.expected_touch
        if command.acceptance is not None:
            work_item.acceptance = command.acceptance
        if command.validation is not None:
            work_item.validation = command.validation

        if command.conflict_keys is not None:
            replace_conflict_keys(session, work_item_id, command.conflict_keys)
        if command.dependency_ids is not None:
            replace_dependencies(session, work_item_id, command.dependency_ids)
        session.add(
            AuditEvent(
                actor=actor,
                action="triage_work_item",
                subject_type="work_item",
                subject_id=work_item.id,
                summary="Work item scheduling facts were triaged.",
                details={"status": work_item.status},
            )
        )
        session.flush()
        return cast(
            JsonObject, work_item_to_read(session, work_item).model_dump(mode="json")
        )

    result = run_idempotent_command(
        session,
        command_name="work_item.triage",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkItemRead.model_validate(result.body)


def validate_triage_command(
    session: Session,
    work_item_id: str,
    command: WorkItemTriageCommand,
) -> None:
    work_item = session.get(WorkItem, work_item_id)
    if work_item is None:
        raise CommandBlockedError(
            "work_item_not_found",
            "Work item does not exist.",
            {"work_item_id": work_item_id},
        )
    if (
        command.status is not None
        and str(command.status) not in ALLOWED_TRIAGE_STATUSES
    ):
        raise CommandBlockedError(
            "invalid_triage_status",
            "Work item triage can only move work to backlog, ready, blocked, "
            "or human decision.",
            {"status": str(command.status)},
        )
    requested_dependency_ids = {
        dependency_id.strip()
        for dependency_id in command.dependency_ids or ()
        if dependency_id.strip()
    }
    if work_item_id in requested_dependency_ids:
        raise CommandBlockedError(
            "self_dependency",
            "Work item cannot depend on itself.",
            {"work_item_id": work_item_id},
        )
    validate_dependency_ids(session, requested_dependency_ids)


def validate_repository_exists(session: Session, repository_id: str | None) -> None:
    if repository_id is None:
        return
    if session.get(Repository, repository_id) is None:
        raise CommandBlockedError(
            "repository_not_found",
            "Repository does not exist.",
            {"repository_id": repository_id},
        )


def validate_dependency_ids(
    session: Session,
    requested_dependency_ids: set[str],
) -> None:
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
            "Work item references dependencies that do not exist.",
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


def replace_conflict_keys(
    session: Session,
    work_item_id: str,
    conflict_keys: Iterable[str],
) -> None:
    session.query(WorkItemConflictKey).filter(
        WorkItemConflictKey.work_item_id == work_item_id
    ).delete()
    add_conflict_keys(session, work_item_id, conflict_keys)


def replace_dependencies(
    session: Session,
    work_item_id: str,
    dependency_ids: Iterable[str],
) -> None:
    session.query(WorkItemDependency).filter(
        WorkItemDependency.work_item_id == work_item_id
    ).delete()
    add_dependencies(session, work_item_id, dependency_ids)


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
