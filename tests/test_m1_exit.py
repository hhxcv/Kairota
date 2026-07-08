from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from kairota.services.demo_data import seed_m1_demo_data
from kairota.services.m1_exit import run_m1_exit_smoke
from kairota.services.queue_workbench import queue_workbench


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


def test_seed_m1_demo_data_populates_workbench_recovery_signals(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session, session.begin():
        seed = seed_m1_demo_data(session)
        workbench = queue_workbench(session)

    assert seed.status == "seeded"
    assert "m1-demo-ready" in seed.work_item_ids
    sections = {section.id: section for section in workbench.sections}
    assert all(sections[section].count > 0 for section in sections)
    assert {row.id for row in workbench.decision_inbox} >= {
        "m1-demo-blocked",
        "m1-demo-review",
        "m1-demo-failed",
    }
    assert {signal.id for signal in workbench.recovery_signals} >= {
        "stale_active_leases",
        "failed_inbound_events",
        "failed_sync_cursors",
        "stale_repository_gates",
    }


def test_m1_exit_smoke_covers_happy_and_failure_paths(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session, session.begin():
        result = run_m1_exit_smoke(
            session,
            idempotency_prefix="test-m1-exit-smoke",
        )

    assert result.status == "passed"
    check_names = {check.name for check in result.checks if check.status == "passed"}
    assert check_names >= {
        "seed_demo_data",
        "schedule_and_claim_ready_work",
        "worker_run_lifecycle_records_evidence",
        "blocked_dependency_rejected",
        "conflict_lock_blocks_second_claim",
        "expired_lease_reconciled",
        "workbench_sections_visible",
        "ci_and_review_gates_visible",
        "recovery_signals_visible",
    }
