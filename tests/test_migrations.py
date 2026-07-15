from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from kairota.config import Settings
from kairota.db import create_sync_engine

NEW_TABLES = {
    "alembic_version",
    "audit_events",
    "command_requests",
    "inbound_events",
    "issue_dependencies",
    "managed_issues",
    "project_sync_states",
    "projects",
}


def migration_config(db_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config


def test_fresh_install_builds_only_simplified_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite"
    config = migration_config(db_path)

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    assert set(inspect(engine).get_table_names()) == NEW_TABLES
    with engine.connect() as connection:
        version = connection.scalar(text("select version_num from alembic_version"))
    assert version == "0006_simplified_issue_scheduler"


def test_upgrade_discards_legacy_rows_once(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    config = migration_config(db_path)
    command.upgrade(config, "0005_managed_project_onboarding")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "insert into work_items "
                "(id, title, status, priority, risk, work_type, autonomy_mode, "
                "created_at, updated_at) "
                "values ('legacy', 'discard me', 'ready', 0, 'low', "
                "'implementation', 'fully_autonomous', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    command.upgrade(config, "head")

    assert set(inspect(engine).get_table_names()) == NEW_TABLES
    assert "work_items" not in inspect(engine).get_table_names()


def test_destructive_revision_has_no_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "no-downgrade.sqlite"
    config = migration_config(db_path)
    command.upgrade(config, "head")

    with pytest.raises(RuntimeError, match="intentionally discards data"):
        command.downgrade(config, "0005_managed_project_onboarding")


def test_runtime_sqlite_enables_foreign_keys_and_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    engine = create_sync_engine(
        Settings(
            database_url=f"sqlite:///{db_path.as_posix()}",
            auto_migrate=False,
        )
    )
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
