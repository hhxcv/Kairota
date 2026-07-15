from __future__ import annotations

import re
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import SyncHealth
from kairota.contracts.schemas import (
    ProjectCreate,
    ProjectRead,
    ProjectSyncStateRead,
    ProjectUpdate,
)
from kairota.models.records import AuditEvent, Project, ProjectSyncState
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command

GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def register_project_command(
    session: Session,
    *,
    command: ProjectCreate,
    idempotency_key: str,
    actor: str = "local",
) -> ProjectRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))

    def execute() -> JsonObject:
        name = normalize_github_name(command.remote)
        project = session.scalar(select(Project).where(Project.name == name))
        created = project is None
        if project is None:
            project = Project(provider_repo_id=name, name=name, enabled=True)
            session.add(project)
            session.flush()
            session.add(
                ProjectSyncState(
                    project_id=project.id,
                    health=SyncHealth.UNKNOWN.value,
                )
            )
        session.add(
            AuditEvent(
                actor=actor,
                action="register_project",
                summary="Registered a GitHub project.",
                details={"project_id": project.id, "created": created},
            )
        )
        session.flush()
        return cast(
            JsonObject,
            project_to_read(session, project).model_dump(mode="json"),
        )

    result = run_idempotent_command(
        session,
        command_name="project.register",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ProjectRead.model_validate(result.body)


def update_project_command(
    session: Session,
    *,
    project_id: str,
    command: ProjectUpdate,
    idempotency_key: str,
    actor: str = "local",
) -> ProjectRead:
    payload: JsonObject = {
        "project_id": project_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        project = require_project(session, project_id)
        project.enabled = command.enabled
        session.add(
            AuditEvent(
                actor=actor,
                action="update_project",
                summary="Updated project scheduling settings.",
                details={"project_id": project.id, "enabled": project.enabled},
            )
        )
        session.flush()
        return cast(
            JsonObject,
            project_to_read(session, project).model_dump(mode="json"),
        )

    result = run_idempotent_command(
        session,
        command_name="project.update",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ProjectRead.model_validate(result.body)


def list_projects(session: Session) -> tuple[ProjectRead, ...]:
    return tuple(
        project_to_read(session, project)
        for project in session.scalars(select(Project).order_by(Project.name))
    )


def get_project(session: Session, project_id: str) -> ProjectRead | None:
    project = session.get(Project, project_id)
    return project_to_read(session, project) if project is not None else None


def require_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise CommandBlockedError(
            "project_not_found",
            "Project does not exist.",
            {"project_id": project_id},
        )
    return project


def project_to_read(session: Session, project: Project) -> ProjectRead:
    sync_state = session.scalar(
        select(ProjectSyncState).where(ProjectSyncState.project_id == project.id)
    )
    if sync_state is None:
        sync_state = ProjectSyncState(
            project_id=project.id,
            health=SyncHealth.UNKNOWN.value,
        )
        session.add(sync_state)
        session.flush()
    return ProjectRead(
        id=project.id,
        provider_repo_id=project.provider_repo_id,
        name=project.name,
        enabled=project.enabled,
        sync=ProjectSyncStateRead(
            health=SyncHealth(sync_state.health),
            last_attempt_at=sync_state.last_attempt_at,
            last_success_at=sync_state.last_success_at,
            last_error=sync_state.last_error,
        ),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def normalize_github_name(value: str) -> str:
    candidate = value.strip()
    for prefix in ("git@github.com:", "https://github.com/", "http://github.com/"):
        if candidate.startswith(prefix):
            candidate = candidate.removeprefix(prefix)
            break
    candidate = candidate.removesuffix(".git").strip("/")
    if not GITHUB_NAME_RE.fullmatch(candidate):
        raise CommandBlockedError(
            "invalid_project_remote",
            "GitHub project must use owner/name or a GitHub remote URL.",
        )
    return candidate
