from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from kairota.contracts.enums import SyncHealth
from kairota.contracts.schemas import ProjectCreate
from kairota.models.records import ProjectSyncState
from kairota.services.github_sync import sync_project
from kairota.services.projects import (
    list_projects,
    normalize_github_name,
    register_project_command,
)


def test_registration_normalizes_remotes_and_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        first = register_project_command(
            session,
            command=ProjectCreate(remote="https://github.com/owner/repo.git"),
            idempotency_key="register-1",
        )
    with session_factory.begin() as session:
        replay = register_project_command(
            session,
            command=ProjectCreate(remote="https://github.com/owner/repo.git"),
            idempotency_key="register-1",
        )
        second_key = register_project_command(
            session,
            command=ProjectCreate(remote="owner/repo"),
            idempotency_key="register-2",
        )
        assert len(list_projects(session)) == 1

    assert first.id == replay.id == second_key.id
    assert normalize_github_name("git@github.com:owner/repo.git") == "owner/repo"


def test_sync_failure_is_persisted_and_recovers(
    session_factory: sessionmaker[Session], github: Any
) -> None:
    with session_factory.begin() as session:
        project = register_project_command(
            session,
            command=ProjectCreate(remote="owner/repo"),
            idempotency_key="register-sync-error",
        )

    github.error = RuntimeError("GitHub temporarily unavailable")
    with session_factory.begin() as session:
        failed = sync_project(session, project_id=project.id, client=github)
        assert failed.status == SyncHealth.ERROR
        assert failed.error == "GitHub temporarily unavailable"

    with session_factory() as session:
        state = session.scalar(select(ProjectSyncState))
        assert state is not None
        assert state.health == SyncHealth.ERROR
        assert state.last_error == "GitHub temporarily unavailable"

    github.error = None
    github.set_issue(1)
    with session_factory.begin() as session:
        recovered = sync_project(session, project_id=project.id, client=github)
        state = session.scalar(select(ProjectSyncState))
        assert recovered.status == SyncHealth.HEALTHY
        assert state is not None and state.last_error is None
