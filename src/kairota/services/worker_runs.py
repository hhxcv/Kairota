from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    LeaseStatus,
    WorkerRunResult,
    WorkerRunStatus,
    WorkItemStatus,
)
from kairota.contracts.schemas import (
    WorkerRunCloseCommand,
    WorkerRunCreateCommand,
    WorkerRunHeartbeatCommand,
    WorkerRunRead,
    WorkerRunReportCommand,
)
from kairota.domain.state_machine import is_work_item_transition_allowed
from kairota.models.records import AuditEvent, Lease, LockHolder, WorkerRun, WorkItem
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command


def create_worker_run_command(
    session: Session,
    *,
    command: WorkerRunCreateCommand,
    idempotency_key: str,
    actor: str = "worker",
) -> WorkerRunRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))

    def execute() -> JsonObject:
        lease = require_active_lease(
            session,
            lease_id=command.lease_id,
            fencing_token=command.fencing_token,
            work_item_id=command.work_item_id,
        )
        require_no_open_worker_run_for_lease(session, lease.id)
        work_item = require_work_item(session, command.work_item_id)
        transition_work_item_if_allowed(
            session,
            work_item,
            WorkItemStatus.IMPLEMENTING,
            actor=actor,
            reason="worker_run_started",
        )
        now = datetime.now(UTC)
        run = WorkerRun(
            work_item_id=command.work_item_id,
            lease_id=lease.id,
            role=str(command.role),
            status=WorkerRunStatus.RUNNING.value,
            started_at=now,
            heartbeat_at=now,
            validation={},
            public_mutations={},
            cost_summary={},
        )
        session.add(run)
        session.flush()
        audit(
            session,
            actor=actor,
            action="create_worker_run",
            subject_id=run.id,
            summary="Worker run started with lease authority.",
            details={"work_item_id": command.work_item_id, "lease_id": lease.id},
        )
        return cast(JsonObject, worker_run_to_read(run).model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="worker_run.create",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkerRunRead.model_validate(result.body)


def heartbeat_worker_run_command(
    session: Session,
    *,
    worker_run_id: str,
    command: WorkerRunHeartbeatCommand,
    idempotency_key: str,
    actor: str = "worker",
) -> WorkerRunRead:
    payload: JsonObject = {
        "worker_run_id": worker_run_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        run = require_open_worker_run(session, worker_run_id)
        if run.lease_id is None:
            raise CommandBlockedError(
                "worker_run_missing_lease",
                "Worker run does not have lease authority.",
                {"worker_run_id": worker_run_id},
            )
        require_active_lease(
            session,
            lease_id=run.lease_id,
            fencing_token=command.fencing_token,
            work_item_id=run.work_item_id,
        )
        run.heartbeat_at = datetime.now(UTC)
        session.flush()
        audit(
            session,
            actor=actor,
            action="heartbeat_worker_run",
            subject_id=run.id,
            summary="Worker run heartbeat refreshed.",
            details={"work_item_id": run.work_item_id},
        )
        return cast(JsonObject, worker_run_to_read(run).model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="worker_run.heartbeat",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkerRunRead.model_validate(result.body)


def report_worker_run_command(
    session: Session,
    *,
    worker_run_id: str,
    command: WorkerRunReportCommand,
    idempotency_key: str,
    actor: str = "worker",
) -> WorkerRunRead:
    payload: JsonObject = {
        "worker_run_id": worker_run_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        run = require_open_worker_run(session, worker_run_id)
        require_worker_run_authority(session, run, command.fencing_token)
        run.status = WorkerRunStatus.REPORTING.value
        run.heartbeat_at = datetime.now(UTC)
        run.validation = merge_json(run.validation, command.validation)
        run.public_mutations = merge_json(
            run.public_mutations, command.public_mutations
        )
        run.cost_summary = merge_json(run.cost_summary, command.cost_summary)
        session.flush()
        audit(
            session,
            actor=actor,
            action="report_worker_run",
            subject_id=run.id,
            summary="Worker run reported validation or public mutation evidence.",
            details={
                "has_validation": bool(command.validation),
                "has_public_mutations": bool(command.public_mutations),
            },
        )
        return cast(JsonObject, worker_run_to_read(run).model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="worker_run.report",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkerRunRead.model_validate(result.body)


def close_worker_run_command(
    session: Session,
    *,
    worker_run_id: str,
    command: WorkerRunCloseCommand,
    idempotency_key: str,
    actor: str = "worker",
) -> WorkerRunRead:
    payload: JsonObject = {
        "worker_run_id": worker_run_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        run = require_open_worker_run(session, worker_run_id)
        lease = require_worker_run_authority(session, run, command.fencing_token)
        now = datetime.now(UTC)
        run.validation = merge_json(run.validation, command.validation)
        run.public_mutations = merge_json(
            run.public_mutations, command.public_mutations
        )
        run.cost_summary = merge_json(run.cost_summary, command.cost_summary)
        run.status = WorkerRunStatus.CLOSED.value
        run.result = str(command.result)
        run.closed_at = now
        run.heartbeat_at = run.closed_at
        apply_close_transition(session, run, command.result, actor=actor)
        release_lease_and_locks(
            session,
            lease,
            released_at=now,
            actor=actor,
            worker_run_id=run.id,
        )
        session.flush()
        audit(
            session,
            actor=actor,
            action="close_worker_run",
            subject_id=run.id,
            summary="Worker run closed with result.",
            details={"result": str(command.result), "work_item_id": run.work_item_id},
        )
        return cast(JsonObject, worker_run_to_read(run).model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="worker_run.close",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return WorkerRunRead.model_validate(result.body)


def get_worker_run(session: Session, worker_run_id: str) -> WorkerRunRead | None:
    run = session.get(WorkerRun, worker_run_id)
    if run is None:
        return None
    return worker_run_to_read(run)


def require_worker_run_authority(
    session: Session,
    run: WorkerRun,
    fencing_token: str,
) -> Lease:
    if run.lease_id is None:
        raise CommandBlockedError(
            "worker_run_missing_lease",
            "Worker run does not have lease authority.",
            {"worker_run_id": run.id},
        )
    return require_active_lease(
        session,
        lease_id=run.lease_id,
        fencing_token=fencing_token,
        work_item_id=run.work_item_id,
    )


def require_no_open_worker_run_for_lease(session: Session, lease_id: str) -> None:
    open_run = session.scalar(
        select(WorkerRun)
        .where(
            WorkerRun.lease_id == lease_id,
            WorkerRun.status != WorkerRunStatus.CLOSED.value,
        )
        .with_for_update()
    )
    if open_run is not None:
        raise CommandBlockedError(
            "worker_run_already_open",
            "Lease already has an open worker run.",
            {"lease_id": lease_id, "worker_run_id": open_run.id},
        )


def require_active_lease(
    session: Session,
    *,
    lease_id: str,
    fencing_token: str,
    work_item_id: str,
) -> Lease:
    lease = session.scalar(select(Lease).where(Lease.id == lease_id).with_for_update())
    if lease is None:
        raise CommandBlockedError(
            "lease_not_found",
            "Lease does not exist.",
            {"lease_id": lease_id},
        )
    if lease.work_item_id != work_item_id:
        raise CommandBlockedError(
            "lease_work_item_mismatch",
            "Lease does not belong to the requested work item.",
            {"lease_id": lease_id, "work_item_id": work_item_id},
        )
    if lease.status != LeaseStatus.ACTIVE.value:
        raise CommandBlockedError(
            "lease_not_active",
            "Lease is not active.",
            {"lease_id": lease_id},
        )
    if lease.fencing_token != fencing_token:
        raise CommandBlockedError(
            "invalid_fencing_token",
            "Fencing token does not match the active lease.",
            {"lease_id": lease_id},
        )
    return lease


def require_work_item(session: Session, work_item_id: str) -> WorkItem:
    work_item = session.scalar(
        select(WorkItem).where(WorkItem.id == work_item_id).with_for_update()
    )
    if work_item is None:
        raise CommandBlockedError(
            "work_item_not_found",
            "Work item does not exist.",
            {"work_item_id": work_item_id},
        )
    return work_item


def require_open_worker_run(session: Session, worker_run_id: str) -> WorkerRun:
    run = session.scalar(
        select(WorkerRun).where(WorkerRun.id == worker_run_id).with_for_update()
    )
    if run is None:
        raise CommandBlockedError(
            "worker_run_not_found",
            "Worker run does not exist.",
            {"worker_run_id": worker_run_id},
        )
    if run.status == WorkerRunStatus.CLOSED.value:
        raise CommandBlockedError(
            "worker_run_closed",
            "Worker run is already closed.",
            {"worker_run_id": worker_run_id},
        )
    return run


def release_lease_and_locks(
    session: Session,
    lease: Lease,
    *,
    released_at: datetime,
    actor: str,
    worker_run_id: str,
) -> None:
    released_lock_ids: list[str] = []
    if lease.status == LeaseStatus.ACTIVE.value:
        lease.status = LeaseStatus.RELEASED.value

    locks = session.scalars(
        select(LockHolder)
        .where(
            LockHolder.lease_id == lease.id,
            LockHolder.released_at.is_(None),
        )
        .with_for_update()
    )
    for lock in locks:
        lock.released_at = released_at
        released_lock_ids.append(lock.id)

    session.add(
        AuditEvent(
            actor=actor,
            action="release_worker_run_lease",
            subject_type="lease",
            subject_id=lease.id,
            summary="Released worker-run lease authority and lease-held locks.",
            details={
                "worker_run_id": worker_run_id,
                "released_lock_ids": tuple(released_lock_ids),
            },
        )
    )


def apply_close_transition(
    session: Session,
    run: WorkerRun,
    result: WorkerRunResult,
    *,
    actor: str,
) -> None:
    work_item = require_work_item(session, run.work_item_id)
    if (
        result == WorkerRunResult.DONE
        and work_item.status == WorkItemStatus.MERGED.value
    ):
        transition_work_item_if_allowed(
            session,
            work_item,
            WorkItemStatus.DONE,
            actor=actor,
            reason="worker_run_done_after_merge",
        )
    elif result == WorkerRunResult.BLOCKED:
        transition_work_item_if_allowed(
            session,
            work_item,
            WorkItemStatus.BLOCKED,
            actor=actor,
            reason="worker_run_blocked",
        )


def transition_work_item_if_allowed(
    session: Session,
    work_item: WorkItem,
    target: WorkItemStatus,
    *,
    actor: str,
    reason: str,
) -> None:
    current = WorkItemStatus(work_item.status)
    if current == target:
        return
    if not is_work_item_transition_allowed(current, target):
        raise CommandBlockedError(
            "work_item_transition_blocked",
            "Worker run command would apply a disallowed work item transition.",
            {"from": current.value, "to": target.value, "reason": reason},
        )
    work_item.status = target.value
    session.add(
        AuditEvent(
            actor=actor,
            action="worker_run_transition",
            subject_type="work_item",
            subject_id=work_item.id,
            summary="Applied worker-run-derived work item transition.",
            details={"from": current.value, "to": target.value, "reason": reason},
        )
    )


def worker_run_to_read(run: WorkerRun) -> WorkerRunRead:
    return WorkerRunRead(
        id=run.id,
        work_item_id=run.work_item_id,
        lease_id=run.lease_id,
        role=run.role,
        status=run.status,
        result=run.result,
        validation=run.validation,
        public_mutations=run.public_mutations,
        cost_summary=run.cost_summary,
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        closed_at=run.closed_at,
    )


def merge_json(
    current: dict[str, object], update: dict[str, object]
) -> dict[str, object]:
    merged = dict(current)
    merged.update(update)
    return merged


def audit(
    session: Session,
    *,
    actor: str,
    action: str,
    subject_id: str,
    summary: str,
    details: JsonObject,
) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            subject_type="worker_run",
            subject_id=subject_id,
            summary=summary,
            details=details,
        )
    )
