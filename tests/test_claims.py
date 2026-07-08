from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    LeaseStatus,
    SchedulerDecisionCode,
    WorkItemStatus,
)
from kairota.scheduler.claims import (
    claim_work_item,
    expire_stale_leases,
    heartbeat_lease,
)


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    db_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def create_ready_work_item(session: Session, work_item_id: str = "wi-1") -> None:
    session.execute(
        text(
            """
            insert into work_items
                (id, title, status, priority, risk, work_type, autonomy_mode,
                 expected_touch, acceptance, validation)
            values
                (:id, :title, 'ready', 10, 'medium', 'implementation',
                 'ai_assisted', 'src/**', 'done', 'pytest')
            """
        ),
        {"id": work_item_id, "title": f"Work item {work_item_id}"},
    )


def status_for(session: Session, work_item_id: str) -> str:
    return str(
        session.execute(
            text("select status from work_items where id = :id"),
            {"id": work_item_id},
        ).scalar_one()
    )


def test_claim_creates_lease_locks_and_marks_work_item_claimed(engine: Engine) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session, session.begin():
        create_ready_work_item(session)
        result = claim_work_item(
            session,
            work_item_id="wi-1",
            owner="slot-1",
            conflict_keys=frozenset({"repo:kairota:path:src/**"}),
            lease_ttl=timedelta(minutes=30),
            now=now,
        )

        assert result.claimed
        assert result.lease_id is not None
        assert result.fencing_token is not None
        assert status_for(session, "wi-1") == WorkItemStatus.CLAIMED.value
        assert (
            session.execute(
                text("select count(*) from lock_holders where lease_id = :lease_id"),
                {"lease_id": result.lease_id},
            ).scalar_one()
            == 1
        )


def test_claim_rejects_conflicting_active_lock(engine: Engine) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session, session.begin():
        create_ready_work_item(session, "wi-1")
        create_ready_work_item(session, "wi-2")
        first = claim_work_item(
            session,
            work_item_id="wi-1",
            owner="slot-1",
            conflict_keys=frozenset({"contract:scheduler"}),
            lease_ttl=timedelta(minutes=30),
            now=now,
        )
        second = claim_work_item(
            session,
            work_item_id="wi-2",
            owner="slot-2",
            conflict_keys=frozenset({"contract:scheduler"}),
            lease_ttl=timedelta(minutes=30),
            now=now,
        )

        assert first.claimed
        assert not second.claimed
        assert second.reason == SchedulerDecisionCode.BLOCKED_BY_CONFLICT_KEY


def test_heartbeat_requires_current_fencing_token(engine: Engine) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session, session.begin():
        create_ready_work_item(session)
        claim = claim_work_item(
            session,
            work_item_id="wi-1",
            owner="slot-1",
            conflict_keys=frozenset({"repo:kairota:path:src/**"}),
            lease_ttl=timedelta(minutes=30),
            now=now,
        )
        assert claim.lease_id is not None
        assert claim.fencing_token is not None

        wrong_token = heartbeat_lease(
            session,
            lease_id=claim.lease_id,
            fencing_token="wrong",
            lease_ttl=timedelta(minutes=30),
            now=now + timedelta(minutes=10),
        )
        right_token = heartbeat_lease(
            session,
            lease_id=claim.lease_id,
            fencing_token=claim.fencing_token,
            lease_ttl=timedelta(minutes=30),
            now=now + timedelta(minutes=10),
        )

        assert not wrong_token.refreshed
        assert right_token.refreshed


def test_expire_stale_leases_releases_locks_and_recovers_ready(engine: Engine) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session, session.begin():
        create_ready_work_item(session)
        claim = claim_work_item(
            session,
            work_item_id="wi-1",
            owner="slot-1",
            conflict_keys=frozenset({"repo:kairota:path:src/**"}),
            lease_ttl=timedelta(minutes=30),
            now=now,
        )
        assert claim.lease_id is not None

    with Session(engine) as session, session.begin():
        result = expire_stale_leases(session, now=now + timedelta(hours=1))
        assert result.expired_lease_ids == (claim.lease_id,)
        assert len(result.released_lock_ids) == 1
        assert status_for(session, "wi-1") == WorkItemStatus.READY.value
        assert (
            session.execute(
                text("select status from leases where id = :id"),
                {"id": claim.lease_id},
            ).scalar_one()
            == LeaseStatus.EXPIRED.value
        )
