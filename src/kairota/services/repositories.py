from __future__ import annotations

import re
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import RepositoryProvider
from kairota.contracts.schemas import RepositoryCreate, RepositoryRead
from kairota.models.records import AuditEvent, Repository
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command

GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def register_repository_command(
    session: Session,
    *,
    command: RepositoryCreate,
    idempotency_key: str,
    actor: str = "local",
) -> RepositoryRead:
    payload = cast(JsonObject, command.model_dump(mode="json"))

    def execute() -> JsonObject:
        if command.provider != RepositoryProvider.GITHUB:
            raise CommandBlockedError(
                "unsupported_provider",
                "Only GitHub repositories are supported.",
                {"provider": str(command.provider)},
            )
        name = normalize_github_name(command.name or command.remote)
        provider_repo_id = (command.provider_repo_id or name).strip()
        if not provider_repo_id:
            raise CommandBlockedError(
                "invalid_repository",
                "Repository provider id cannot be blank.",
            )

        repository = find_repository(session, provider_repo_id, name)
        created = repository is None
        if repository is None:
            repository = Repository(
                provider=RepositoryProvider.GITHUB.value,
                provider_repo_id=provider_repo_id,
                name=name,
                default_branch=command.default_branch,
                sync_status="unknown",
            )
            session.add(repository)
            session.flush()
        else:
            repository.provider_repo_id = provider_repo_id
            repository.name = name
            repository.default_branch = command.default_branch

        session.add(
            AuditEvent(
                actor=actor,
                action="register_repository",
                subject_type="repository",
                subject_id=repository.id,
                summary="Repository registered for managed project scheduling.",
                details={"provider": repository.provider, "created": created},
            )
        )
        session.flush()
        return cast(JsonObject, repository_to_read(repository).model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="repository.register",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return RepositoryRead.model_validate(result.body)


def list_repositories(session: Session) -> tuple[RepositoryRead, ...]:
    repositories = session.scalars(select(Repository).order_by(Repository.name))
    return tuple(repository_to_read(repository) for repository in repositories)


def get_repository(session: Session, repository_id: str) -> RepositoryRead | None:
    repository = session.get(Repository, repository_id)
    if repository is None:
        return None
    return repository_to_read(repository)


def find_repository(
    session: Session,
    provider_repo_id: str,
    name: str,
) -> Repository | None:
    return session.scalar(
        select(Repository).where(
            Repository.provider == RepositoryProvider.GITHUB.value,
            (
                (Repository.provider_repo_id == provider_repo_id)
                | (Repository.name == name)
            ),
        )
    )


def repository_to_read(repository: Repository) -> RepositoryRead:
    return RepositoryRead(
        id=repository.id,
        provider=RepositoryProvider(repository.provider),
        provider_repo_id=repository.provider_repo_id,
        name=repository.name,
        default_branch=repository.default_branch,
        sync_status=repository.sync_status,
    )


def normalize_github_name(value: str | None) -> str:
    if value is None or not value.strip():
        raise CommandBlockedError(
            "invalid_repository",
            "Repository name or remote URL is required.",
        )
    candidate = value.strip()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif candidate.startswith("https://github.com/"):
        candidate = candidate.removeprefix("https://github.com/")
    elif candidate.startswith("http://github.com/"):
        candidate = candidate.removeprefix("http://github.com/")
    candidate = candidate.removesuffix(".git").strip("/")
    if not GITHUB_NAME_RE.match(candidate):
        raise CommandBlockedError(
            "invalid_repository_name",
            "GitHub repository must be provided as owner/name or a GitHub remote URL.",
            {"value": value},
        )
    return candidate
