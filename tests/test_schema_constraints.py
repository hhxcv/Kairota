from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError


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


def insert_work_item(engine: Engine, work_item_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into work_items
                    (id, title, status, priority, risk, work_type, autonomy_mode)
                values
                    (:id, :title, 'ready', 10, 'medium', 'implementation',
                     'ai_assisted')
                """
            ),
            {"id": work_item_id, "title": f"Work item {work_item_id}"},
        )


def test_dependency_cannot_reference_itself(migrated_engine: Engine) -> None:
    insert_work_item(migrated_engine, "wi-1")

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                    insert into work_item_dependencies
                        (id, work_item_id, depends_on_work_item_id)
                    values ('dep-1', 'wi-1', 'wi-1')
                    """
            )
        )


def test_one_active_lease_per_work_item(migrated_engine: Engine) -> None:
    insert_work_item(migrated_engine, "wi-1")

    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into leases
                    (id, work_item_id, owner, status, fencing_token, expires_at)
                values
                    ('lease-1', 'wi-1', 'slot-1', 'active', 'token-1',
                     '2026-01-01T00:00:00Z')
                """
            )
        )

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                    insert into leases
                        (id, work_item_id, owner, status, fencing_token,
                         expires_at)
                    values
                        ('lease-2', 'wi-1', 'slot-2', 'active', 'token-2',
                         '2026-01-01T00:00:00Z')
                    """
            )
        )

    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into leases
                    (id, work_item_id, owner, status, fencing_token, expires_at)
                values
                    ('lease-3', 'wi-1', 'slot-3', 'released', 'token-3',
                     '2026-01-01T00:00:00Z')
                """
            )
        )


def test_one_active_lock_holder_per_conflict_key(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into lock_holders (id, conflict_key, source)
                values ('lock-1', 'repo:kairota:path:src/**', 'fallback')
                """
            )
        )

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                    insert into lock_holders (id, conflict_key, source)
                    values ('lock-2', 'repo:kairota:path:src/**', 'fallback')
                    """
            )
        )

    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into lock_holders
                    (id, conflict_key, source, released_at)
                values
                    ('lock-3', 'repo:kairota:path:src/**', 'fallback',
                     '2026-01-01T00:00:00Z')
                """
            )
        )


def test_inbound_events_are_idempotent_per_provider(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                insert into inbound_events
                    (id, provider, idempotency_key, event_type, payload_hash,
                     status)
                values
                    ('event-1', 'github', 'delivery-1', 'pull_request',
                     'hash-1', 'pending')
                """
            )
        )

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.execute(
            text(
                """
                    insert into inbound_events
                        (id, provider, idempotency_key, event_type,
                         payload_hash, status)
                    values
                        ('event-2', 'github', 'delivery-1', 'pull_request',
                         'hash-2', 'pending')
                    """
            )
        )
