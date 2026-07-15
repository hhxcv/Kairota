from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from kairota.contracts.enums import SchedulingState, SyncHealth
from kairota.contracts.schemas import (
    IssueAnalysisCommand,
    IssueClaimCommand,
    IssueReleaseCommand,
    ProjectCreate,
)
from kairota.models.records import ManagedIssue, ProjectSyncState
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import sync_project
from kairota.services.issues import (
    analyze_issue_command,
    claim_issue_command,
    get_issue_read,
    release_issue_command,
)
from kairota.services.projects import register_project_command


def register_and_sync(
    factory: sessionmaker[Session], github: Any, numbers: range = range(1, 4)
) -> tuple[str, dict[int, str]]:
    for number in numbers:
        github.set_issue(number)
    with factory.begin() as session:
        project = register_project_command(
            session,
            command=ProjectCreate(remote="owner/repo"),
            idempotency_key="register",
        )
        sync_project(session, project_id=project.id, client=github)
        ids = {
            issue.number: issue.id
            for issue in session.scalars(select(ManagedIssue))
        }
    return project.id, ids


def analyze(
    session: Session,
    issue_id: str,
    *,
    dependencies: tuple[int, ...] = (),
    hold: str | None = None,
    key: str,
) -> None:
    issue = get_issue_read(session, issue_id)
    assert issue is not None
    analyze_issue_command(
        session,
        issue_id=issue_id,
        command=IssueAnalysisCommand(
            expected_analysis_version=issue.analysis_version,
            dependency_issue_numbers=dependencies,
            manual_hold_reason=hold,
        ),
        idempotency_key=key,
    )


def test_dependencies_close_reopen_and_manual_hold_drive_five_states(
    session_factory: sessionmaker[Session], github: Any
) -> None:
    project_id, ids = register_and_sync(session_factory, github)
    with session_factory.begin() as session:
        analyze(session, ids[1], key="analyze-1")
        analyze(session, ids[2], dependencies=(1,), key="analyze-2")
        analyze(session, ids[3], hold="waiting for product decision", key="analyze-3")
        assert get_issue_read(session, ids[1]).scheduling_state == "ready"  # type: ignore[union-attr]
        assert get_issue_read(session, ids[2]).scheduling_state == "blocked"  # type: ignore[union-attr]
        assert get_issue_read(session, ids[3]).scheduling_state == "blocked"  # type: ignore[union-attr]

    github.set_issue(1, state="closed")
    with session_factory.begin() as session:
        result = sync_project(
            session,
            project_id=project_id,
            client=github,
            issue_numbers=(1,),
        )
        assert result.transitions_applied == 2
        assert get_issue_read(session, ids[1]).scheduling_state == "closed"  # type: ignore[union-attr]
        assert get_issue_read(session, ids[2]).scheduling_state == "ready"  # type: ignore[union-attr]

    github.set_issue(1, state="open")
    with session_factory.begin() as session:
        sync_project(
            session,
            project_id=project_id,
            client=github,
            issue_numbers=(1,),
        )
        reopened = get_issue_read(session, ids[1])
        dependent = get_issue_read(session, ids[2])
        assert reopened is not None and reopened.scheduling_state == "needs_analysis"
        assert reopened.analysis_completed is False
        assert dependent is not None and dependent.scheduling_state == "blocked"


def test_claim_and_release_are_versioned_and_release_invalidates_analysis(
    session_factory: sessionmaker[Session], github: Any
) -> None:
    _project_id, ids = register_and_sync(session_factory, github, range(1, 2))
    with session_factory.begin() as session:
        analyze(session, ids[1], key="analyze")
        ready = get_issue_read(session, ids[1])
        assert ready is not None
        claimed = claim_issue_command(
            session,
            issue_id=ids[1],
            command=IssueClaimCommand(
                expected_scheduling_version=ready.scheduling_version
            ),
            idempotency_key="claim",
        )
        assert claimed.scheduling_state == SchedulingState.IN_PROGRESS

    with session_factory.begin() as session:
        with pytest.raises(CommandBlockedError) as conflict:
            claim_issue_command(
                session,
                issue_id=ids[1],
                command=IssueClaimCommand(
                    expected_scheduling_version=ready.scheduling_version
                ),
                idempotency_key="second-claim",
            )
        assert conflict.value.reason_code == "state_in_progress"

    with session_factory.begin() as session:
        current = get_issue_read(session, ids[1])
        assert current is not None
        released = release_issue_command(
            session,
            issue_id=ids[1],
            command=IssueReleaseCommand(
                expected_scheduling_version=current.scheduling_version,
                reason="Main AI restarted and cannot confirm worker ownership.",
            ),
            idempotency_key="release",
        )
        assert released.scheduling_state == SchedulingState.NEEDS_ANALYSIS
        assert released.analysis_completed is False
        assert released.dependencies == ()
        assert released.analysis_version == ready.analysis_version + 1


def test_cycle_and_cross_project_dependency_are_rejected(
    session_factory: sessionmaker[Session], github: Any
) -> None:
    _project_id, ids = register_and_sync(session_factory, github, range(1, 3))
    with session_factory.begin() as session:
        analyze(session, ids[1], dependencies=(2,), key="edge-1-2")
        with pytest.raises(CommandBlockedError) as cycle:
            analyze(session, ids[2], dependencies=(1,), key="edge-2-1")
        assert cycle.value.reason_code == "dependency_cycle"

        issue = get_issue_read(session, ids[2])
        assert issue is not None
        with pytest.raises(CommandBlockedError) as missing:
            analyze_issue_command(
                session,
                issue_id=ids[2],
                command=IssueAnalysisCommand(
                    expected_analysis_version=issue.analysis_version,
                    dependency_issue_numbers=(999,),
                ),
                idempotency_key="missing-dependency",
            )
        assert missing.value.reason_code == "dependency_not_found"


@pytest.mark.parametrize(
    ("health", "last_success", "reason"),
    [
        (SyncHealth.ERROR, datetime.now(UTC), "sync_unhealthy"),
        (SyncHealth.HEALTHY, datetime.now(UTC) - timedelta(hours=1), "sync_stale"),
    ],
)
def test_claim_requires_recent_healthy_sync(
    session_factory: sessionmaker[Session],
    github: Any,
    health: SyncHealth,
    last_success: datetime,
    reason: str,
) -> None:
    _project_id, ids = register_and_sync(session_factory, github, range(1, 2))
    with session_factory.begin() as session:
        analyze(session, ids[1], key=f"analyze-{reason}")
        sync_state = session.scalar(select(ProjectSyncState))
        assert sync_state is not None
        sync_state.health = health.value
        sync_state.last_success_at = last_success
        ready = get_issue_read(session, ids[1], sync_stale_after_seconds=300)
        assert ready is not None
        assert ready.claimable_now is False
        assert ready.claim_block_reason == reason
        with pytest.raises(CommandBlockedError) as blocked:
            claim_issue_command(
                session,
                issue_id=ids[1],
                command=IssueClaimCommand(
                    expected_scheduling_version=ready.scheduling_version
                ),
                idempotency_key=f"claim-{reason}",
                sync_stale_after_seconds=300,
            )
        assert blocked.value.reason_code == reason
