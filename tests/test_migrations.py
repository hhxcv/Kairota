from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_baseline_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "alembic_version",
        "audit_events",
        "external_refs",
        "inbound_events",
        "leases",
        "lock_holders",
        "outbox_events",
        "repo_check_summaries",
        "repo_pull_requests",
        "repo_review_summaries",
        "repositories",
        "scheduler_cycles",
        "scheduler_decisions",
        "scheduler_guards",
        "sync_cursors",
        "work_item_conflict_keys",
        "work_item_dependencies",
        "work_items",
        "worker_runs",
    } <= tables

    command.downgrade(config, "base")
    with engine.connect() as connection:
        row_count = connection.execute(text("select count(*) from alembic_version"))
        assert row_count.scalar_one() == 0
