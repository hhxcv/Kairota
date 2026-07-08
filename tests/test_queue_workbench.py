from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    EventStatus,
    LeaseStatus,
    RepositoryProvider,
    ReviewGateState,
    WorkerRole,
    WorkerRunStatus,
    WorkItemStatus,
)
from kairota.models.records import (
    AuditEvent,
    InboundEvent,
    Lease,
    RepoCheckSummary,
    RepoPullRequest,
    RepoReviewSummary,
    Repository,
    WorkerRun,
    WorkItem,
    WorkItemConflictKey,
)
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


def test_queue_workbench_groups_sections_and_decision_inbox(
    migrated_engine: Engine,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(migrated_engine) as session, session.begin():
        ready = add_work_item(session, "ready-1", WorkItemStatus.READY)
        running = add_work_item(session, "running-1", WorkItemStatus.IMPLEMENTING)
        blocked = add_work_item(session, "blocked-1", WorkItemStatus.HUMAN_DECISION)
        waiting = add_work_item(session, "waiting-1", WorkItemStatus.WAITING_CHECKS)
        failed = add_work_item(session, "failed-1", WorkItemStatus.CI_FAILED)
        add_work_item(session, "done-1", WorkItemStatus.DONE)
        blocked_id = blocked.id
        failed_id = failed.id
        session.add(
            WorkItemConflictKey(
                work_item_id=ready.id,
                conflict_key="runtime:frontend",
            )
        )
        lease = Lease(
            work_item_id=running.id,
            owner="slot-1",
            status=LeaseStatus.ACTIVE.value,
            fencing_token="token-1",
            heartbeat_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        session.add(lease)
        session.flush()
        session.add(
            WorkerRun(
                work_item_id=running.id,
                lease_id=lease.id,
                role=WorkerRole.WORKER.value,
                status=WorkerRunStatus.RUNNING.value,
                heartbeat_at=now,
                validation={},
                public_mutations={},
                cost_summary={},
            )
        )
        repository = Repository(
            provider=RepositoryProvider.GITHUB.value,
            provider_repo_id="repo-1",
            name="owner/repo",
            default_branch="main",
            sync_status="ok",
        )
        session.add(repository)
        session.flush()
        pull_request = RepoPullRequest(
            repository_id=repository.id,
            work_item_id=waiting.id,
            provider_pr_id="pr-7",
            number=7,
            url="https://example.test/pr/7",
            state="open",
            draft=False,
            head_sha="abc123",
            merged=False,
        )
        session.add(pull_request)
        session.flush()
        session.add_all(
            [
                RepoCheckSummary(
                    pull_request_id=pull_request.id,
                    name="pytest",
                    status=CheckStatus.COMPLETED.value,
                    conclusion=CheckConclusion.SUCCESS.value,
                    required=True,
                    stale=False,
                ),
                RepoReviewSummary(
                    pull_request_id=pull_request.id,
                    state=ReviewGateState.WAITING.value,
                    unresolved_count=1,
                    stale=False,
                ),
                AuditEvent(
                    actor="test",
                    action="create_work_item",
                    subject_type="work_item",
                    subject_id=ready.id,
                    summary="Ready work created.",
                    details={"status": "ready"},
                ),
                InboundEvent(
                    provider=RepositoryProvider.GITHUB.value,
                    idempotency_key="delivery-1",
                    event_type="pull_request",
                    action="synchronize",
                    payload_hash="hash",
                    status=EventStatus.FAILED.value,
                ),
            ]
        )

        result = queue_workbench(session)

    sections = {section.id: section for section in result.sections}
    assert tuple(sections) == (
        "ready",
        "running",
        "blocked",
        "waiting",
        "failed",
        "done",
    )
    assert sections["ready"].count == 1
    assert sections["running"].rows[0].worker_run is not None
    assert sections["running"].rows[0].worker_run.status == WorkerRunStatus.RUNNING
    assert sections["blocked"].rows[0].reason_code == "blocked_by_human_decision"
    assert sections["waiting"].rows[0].repository["pull_request_number"] == 7
    assert sections["failed"].rows[0].reason_code == "blocked_by_ci"
    assert sections["done"].rows[0].next_action == "No action"
    assert {row.id for row in result.decision_inbox} == {blocked_id, failed_id}
    assert result.recent_events[0].summary == "Ready work created."
    assert result.failures[0].kind == "inbound_event"


def add_work_item(
    session: Session,
    work_item_id: str,
    status: WorkItemStatus,
) -> WorkItem:
    work_item = WorkItem(
        id=work_item_id,
        title=f"{status.value} work",
        status=status.value,
        priority=10,
        risk="medium",
        work_type="implementation",
        autonomy_mode="ai_assisted",
        expected_touch="web/src/**",
        acceptance="Visible in workbench",
        validation="pytest",
    )
    session.add(work_item)
    return work_item
