from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    LeaseStatus,
    WorkerRunResult,
    WorkerRunStatus,
    WorkItemStatus,
)
from kairota.contracts.schemas import (
    ClaimWorkItemCommand,
    ClaimWorkItemRead,
    WorkerRunCloseCommand,
    WorkerRunCreateCommand,
    WorkerRunHeartbeatCommand,
    WorkerRunReportCommand,
    WorkItemCreate,
)
from kairota.models.records import Lease, LockHolder, WorkItem
from kairota.services.errors import CommandBlockedError
from kairota.services.scheduler_cycles import claim_work_item_command
from kairota.services.work_items import create_work_item_command
from kairota.services.worker_runs import (
    close_worker_run_command,
    create_worker_run_command,
    heartbeat_worker_run_command,
    report_worker_run_command,
)


@pytest.fixture()
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def test_worker_run_lifecycle_records_evidence_and_closes_done(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session, session.begin():
        work_item = create_ready_work_item(session, idempotency_key="lifecycle-work")
        claim = claim_ready_work(
            session, work_item.id, idempotency_key="lifecycle-claim"
        )
        assert claim.lease_id is not None
        assert claim.fencing_token is not None

        run = create_worker_run_command(
            session,
            command=WorkerRunCreateCommand(
                work_item_id=work_item.id,
                lease_id=claim.lease_id,
                fencing_token=claim.fencing_token,
            ),
            idempotency_key="lifecycle-run",
            actor="test",
        )

        assert run.status == WorkerRunStatus.RUNNING.value
        assert run.lease_id == claim.lease_id
        assert run.started_at is not None
        assert run.heartbeat_at is not None
        assert session.get(WorkItem, work_item.id).status == WorkItemStatus.IMPLEMENTING

        heartbeat = heartbeat_worker_run_command(
            session,
            worker_run_id=run.id,
            command=WorkerRunHeartbeatCommand(fencing_token=claim.fencing_token),
            idempotency_key="lifecycle-heartbeat",
            actor="test",
        )
        assert heartbeat.status == WorkerRunStatus.RUNNING.value
        assert heartbeat.heartbeat_at is not None

        report = report_worker_run_command(
            session,
            worker_run_id=run.id,
            command=WorkerRunReportCommand(
                fencing_token=claim.fencing_token,
                validation={"pytest": "passed"},
                public_mutations={"pr": 7},
            ),
            idempotency_key="lifecycle-report",
            actor="test",
        )
        assert report.status == WorkerRunStatus.REPORTING.value
        assert report.validation["pytest"] == "passed"
        assert report.public_mutations["pr"] == 7

        stored_work = session.get(WorkItem, work_item.id)
        assert stored_work is not None
        stored_work.status = WorkItemStatus.MERGED.value

        closed = close_worker_run_command(
            session,
            worker_run_id=run.id,
            command=WorkerRunCloseCommand(
                fencing_token=claim.fencing_token,
                result=WorkerRunResult.DONE,
                validation={"mypy": "passed"},
            ),
            idempotency_key="lifecycle-close",
            actor="test",
        )

        assert closed.status == WorkerRunStatus.CLOSED.value
        assert closed.result == WorkerRunResult.DONE.value
        assert closed.closed_at is not None
        assert closed.validation == {"pytest": "passed", "mypy": "passed"}
        assert session.get(WorkItem, work_item.id).status == WorkItemStatus.DONE.value
        stored_lease = session.get(Lease, claim.lease_id)
        assert stored_lease is not None
        assert stored_lease.status == LeaseStatus.RELEASED.value
        lease_locks = tuple(
            session.scalars(
                select(LockHolder).where(LockHolder.lease_id == claim.lease_id)
            )
        )
        assert lease_locks
        assert all(lock.released_at is not None for lock in lease_locks)


def test_worker_run_create_rejects_missing_lease(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session, session.begin():
        work_item = create_ready_work_item(
            session, idempotency_key="missing-lease-work"
        )

        with pytest.raises(CommandBlockedError) as exc_info:
            create_worker_run_command(
                session,
                command=WorkerRunCreateCommand(
                    work_item_id=work_item.id,
                    lease_id="missing-lease",
                    fencing_token="missing-token",
                ),
                idempotency_key="missing-lease-run",
                actor="test",
            )

        assert exc_info.value.reason_code == "lease_not_found"


def test_worker_run_commands_reject_stale_fencing_token(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session, session.begin():
        work_item = create_ready_work_item(session, idempotency_key="stale-work")
        claim = claim_ready_work(session, work_item.id, idempotency_key="stale-claim")
        assert claim.lease_id is not None
        assert claim.fencing_token is not None
        run = create_worker_run_command(
            session,
            command=WorkerRunCreateCommand(
                work_item_id=work_item.id,
                lease_id=claim.lease_id,
                fencing_token=claim.fencing_token,
            ),
            idempotency_key="stale-run",
            actor="test",
        )

        with pytest.raises(CommandBlockedError) as exc_info:
            heartbeat_worker_run_command(
                session,
                worker_run_id=run.id,
                command=WorkerRunHeartbeatCommand(fencing_token="stale-token"),
                idempotency_key="stale-heartbeat",
                actor="test",
            )

        assert exc_info.value.reason_code == "invalid_fencing_token"


def test_worker_run_create_rejects_second_open_run(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session, session.begin():
        work_item = create_ready_work_item(session, idempotency_key="duplicate-work")
        claim = claim_ready_work(
            session, work_item.id, idempotency_key="duplicate-claim"
        )
        assert claim.lease_id is not None
        assert claim.fencing_token is not None
        create_worker_run_command(
            session,
            command=WorkerRunCreateCommand(
                work_item_id=work_item.id,
                lease_id=claim.lease_id,
                fencing_token=claim.fencing_token,
            ),
            idempotency_key="duplicate-run-first",
            actor="test",
        )

        with pytest.raises(CommandBlockedError) as exc_info:
            create_worker_run_command(
                session,
                command=WorkerRunCreateCommand(
                    work_item_id=work_item.id,
                    lease_id=claim.lease_id,
                    fencing_token=claim.fencing_token,
                ),
                idempotency_key="duplicate-run-second",
                actor="test",
            )

        assert exc_info.value.reason_code == "worker_run_already_open"


def create_ready_work_item(session: Session, *, idempotency_key: str) -> WorkItem:
    created = create_work_item_command(
        session,
        command=WorkItemCreate(
            title=f"Worker run test {idempotency_key}",
            status=WorkItemStatus.READY,
            priority=10,
            expected_touch="src/kairota/services/worker_runs.py",
            acceptance="Worker run lifecycle is recorded.",
            validation="pytest",
            conflict_keys=("runtime:worker",),
        ),
        idempotency_key=idempotency_key,
        actor="test",
    )
    work_item = session.get(WorkItem, created.id)
    assert work_item is not None
    return work_item


def claim_ready_work(
    session: Session, work_item_id: str, *, idempotency_key: str
) -> ClaimWorkItemRead:
    return claim_work_item_command(
        session,
        work_item_id=work_item_id,
        command=ClaimWorkItemCommand(owner="slot-1"),
        idempotency_key=idempotency_key,
    )
