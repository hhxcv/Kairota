from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from kairota.adapters.github.models import (
    GitHubClient,
    GitHubIssueSnapshot,
    GitHubProjectConfig,
    GitHubSyncSnapshot,
    GitHubWebhookEvent,
)
from kairota.contracts.enums import (
    EventStatus,
    IssueSourceState,
    SchedulingState,
    SyncHealth,
)
from kairota.contracts.schemas import ProjectSyncRead
from kairota.models.records import (
    AuditEvent,
    InboundEvent,
    ManagedIssue,
    Project,
    ProjectSyncState,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command
from kairota.services.issues import (
    invalidate_analysis,
    recompute_dependents,
    recompute_issue_state,
)


@dataclass
class SyncStats:
    issues_seen: int = 0
    issues_created: int = 0
    issues_updated: int = 0
    transitions_applied: int = 0


_locks_guard = Lock()
_project_locks: dict[str, Lock] = {}


def sync_project_command(
    session: Session,
    *,
    project_id: str,
    idempotency_key: str,
    client: GitHubClient,
) -> ProjectSyncRead:
    payload: JsonObject = {"project_id": project_id}

    def execute() -> JsonObject:
        result = sync_project(session, project_id=project_id, client=client)
        return cast(JsonObject, result.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="project.sync",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    body = dict(result.body)
    body["replayed"] = result.replayed
    return ProjectSyncRead.model_validate(body)


def sync_project(
    session: Session,
    *,
    project_id: str,
    client: GitHubClient,
    issue_numbers: tuple[int, ...] = (),
    actor: str = "github-sync",
) -> ProjectSyncRead:
    project = session.get(Project, project_id)
    if project is None:
        raise CommandBlockedError(
            "project_not_found",
            "Project does not exist.",
            {"project_id": project_id},
        )
    lock = project_lock(project.id)
    with lock:
        return sync_project_locked(
            session,
            project=project,
            client=client,
            issue_numbers=issue_numbers,
            actor=actor,
        )


def sync_project_locked(
    session: Session,
    *,
    project: Project,
    client: GitHubClient,
    issue_numbers: tuple[int, ...],
    actor: str,
) -> ProjectSyncRead:
    sync_state = require_sync_state(session, project.id)
    sync_state.health = SyncHealth.SYNCING.value
    sync_state.last_attempt_at = datetime.now(UTC)
    sync_state.last_error = None
    session.flush()

    try:
        snapshot = client.fetch_project_snapshot(
            project_config(project), issue_numbers=issue_numbers
        )
        validate_snapshot(project, snapshot)
        stats = apply_snapshot(session, project, snapshot, actor=actor)
    except Exception as exc:  # GitHub/network/parser failures are sync health facts.
        sync_state.health = SyncHealth.ERROR.value
        sync_state.last_error = safe_error(exc)
        session.add(
            AuditEvent(
                actor=actor,
                action="sync_project_failed",
                summary="GitHub Issue synchronization failed.",
                details={"project_id": project.id, "error": safe_error(exc)},
            )
        )
        session.flush()
        return ProjectSyncRead(
            project_id=project.id,
            status=SyncHealth.ERROR,
            error=sync_state.last_error,
        )

    sync_state.health = SyncHealth.HEALTHY.value
    sync_state.last_success_at = datetime.now(UTC)
    sync_state.last_error = None
    session.add(
        AuditEvent(
            actor=actor,
            action="sync_project",
            summary="Synchronized GitHub Issue facts.",
            details={
                "project_id": project.id,
                "issue_numbers": list(issue_numbers),
                "issues_seen": stats.issues_seen,
                "transitions_applied": stats.transitions_applied,
            },
        )
    )
    session.flush()
    return ProjectSyncRead(
        project_id=project.id,
        status=SyncHealth.HEALTHY,
        issues_seen=stats.issues_seen,
        issues_created=stats.issues_created,
        issues_updated=stats.issues_updated,
        transitions_applied=stats.transitions_applied,
    )


def process_webhook(
    session: Session,
    *,
    event: GitHubWebhookEvent,
    client: GitHubClient,
) -> ProjectSyncRead:
    existing = session.scalar(
        select(InboundEvent).where(InboundEvent.delivery_id == event.delivery_id)
    )
    if existing is not None and existing.payload_hash != event.payload_hash:
        raise CommandBlockedError(
            "webhook_delivery_conflict",
            "GitHub delivery ID was reused with different content.",
        )

    project = session.scalar(
        select(Project).where(
            or_(
                Project.name == event.project_name,
                Project.provider_repo_id == event.provider_repo_id,
            )
        )
    )
    if project is None:
        raise CommandBlockedError(
            "project_not_registered",
            "Register the GitHub project before sending Issue webhooks.",
            {"project": event.project_name},
        )

    if existing is not None and existing.status == EventStatus.PROCESSED.value:
        return ProjectSyncRead(
            project_id=project.id,
            status=current_sync_health(session, project.id),
            replayed=True,
            inbound_event_id=existing.id,
        )

    inbound = existing or InboundEvent(
        project_id=project.id,
        delivery_id=event.delivery_id,
        event_type=event.event_type,
        action=event.action,
        issue_number=event.issue_number,
        payload_hash=event.payload_hash,
        status=EventStatus.PENDING.value,
    )
    if existing is None:
        session.add(inbound)
    else:
        inbound.status = EventStatus.PENDING.value
        inbound.error = None
    session.flush()

    result = sync_project(
        session,
        project_id=project.id,
        client=client,
        issue_numbers=(event.issue_number,),
        actor="github-webhook",
    )
    inbound.status = (
        EventStatus.PROCESSED.value
        if result.status == SyncHealth.HEALTHY
        else EventStatus.FAILED.value
    )
    inbound.error = result.error
    session.flush()
    return result.model_copy(update={"inbound_event_id": inbound.id})


def sync_enabled_projects(
    session_factory: sessionmaker[Session], client: GitHubClient
) -> tuple[ProjectSyncRead, ...]:
    with session_factory() as session:
        project_ids = tuple(
            session.scalars(select(Project.id).where(Project.enabled.is_(True)))
        )
    results: list[ProjectSyncRead] = []
    for project_id in project_ids:
        with session_factory.begin() as session:
            results.append(sync_project(session, project_id=project_id, client=client))
    return tuple(results)


def apply_snapshot(
    session: Session,
    project: Project,
    snapshot: GitHubSyncSnapshot,
    *,
    actor: str,
) -> SyncStats:
    stats = SyncStats()
    project.provider_repo_id = snapshot.project.provider_repo_id
    project.name = snapshot.project.name
    for source_issue in snapshot.issues:
        stats.issues_seen += 1
        upsert_issue(session, project, source_issue, stats, actor=actor)
    session.flush()
    return stats


def upsert_issue(
    session: Session,
    project: Project,
    source: GitHubIssueSnapshot,
    stats: SyncStats,
    *,
    actor: str,
) -> ManagedIssue:
    issue = session.scalar(
        select(ManagedIssue).where(
            ManagedIssue.project_id == project.id,
            or_(
                ManagedIssue.provider_issue_id == source.provider_issue_id,
                ManagedIssue.number == source.number,
            ),
        )
    )
    now = datetime.now(UTC)
    source_state = IssueSourceState(source.state)
    if issue is None:
        scheduling_state = (
            SchedulingState.CLOSED
            if source_state == IssueSourceState.CLOSED
            else SchedulingState.NEEDS_ANALYSIS
        )
        issue = ManagedIssue(
            project_id=project.id,
            provider_issue_id=source.provider_issue_id,
            number=source.number,
            title=source.title,
            url=source.url,
            source_state=source_state.value,
            scheduling_state=scheduling_state.value,
            source_updated_at=source.updated_at,
            last_synced_at=now,
        )
        session.add(issue)
        session.flush()
        stats.issues_created += 1
        audit_issue_sync(session, issue, actor=actor, action="sync_issue_created")
        return issue

    previous_state = IssueSourceState(issue.source_state)
    changed = any(
        (
            issue.provider_issue_id != source.provider_issue_id,
            issue.number != source.number,
            issue.title != source.title,
            issue.url != source.url,
            previous_state != source_state,
            issue.source_updated_at != source.updated_at,
        )
    )
    issue.provider_issue_id = source.provider_issue_id
    issue.number = source.number
    issue.title = source.title
    issue.url = source.url
    issue.source_updated_at = source.updated_at
    issue.last_synced_at = now

    if previous_state != source_state:
        issue.source_state = source_state.value
        if previous_state == IssueSourceState.CLOSED:
            invalidate_analysis(session, issue)
        else:
            stats.transitions_applied += int(recompute_issue_state(session, issue))
        session.flush()
        stats.transitions_applied += recompute_dependents(session, issue.id)
    if changed:
        stats.issues_updated += 1
        audit_issue_sync(session, issue, actor=actor, action="sync_issue_updated")
    return issue


def project_config(project: Project) -> GitHubProjectConfig:
    try:
        owner, name = project.name.split("/", 1)
    except ValueError as exc:
        raise CommandBlockedError(
            "invalid_project_name", "GitHub project name must use owner/name."
        ) from exc
    if not owner or not name:
        raise CommandBlockedError(
            "invalid_project_name", "GitHub project name must use owner/name."
        )
    return GitHubProjectConfig(
        owner=owner,
        name=name,
        provider_repo_id=project.provider_repo_id,
    )


def validate_snapshot(project: Project, snapshot: GitHubSyncSnapshot) -> None:
    if snapshot.project.name.casefold() != project.name.casefold():
        raise ValueError("GitHub returned a different project than requested.")


def require_sync_state(session: Session, project_id: str) -> ProjectSyncState:
    sync_state = session.scalar(
        select(ProjectSyncState).where(ProjectSyncState.project_id == project_id)
    )
    if sync_state is None:
        sync_state = ProjectSyncState(project_id=project_id)
        session.add(sync_state)
        session.flush()
    return sync_state


def current_sync_health(session: Session, project_id: str) -> SyncHealth:
    state = require_sync_state(session, project_id)
    return SyncHealth(state.health)


def project_lock(project_id: str) -> Lock:
    with _locks_guard:
        return _project_locks.setdefault(project_id, Lock())


def audit_issue_sync(
    session: Session, issue: ManagedIssue, *, actor: str, action: str
) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            issue_id=issue.id,
            summary="Synchronized GitHub Issue facts.",
            details={
                "project_id": issue.project_id,
                "issue_number": issue.number,
                "source_state": issue.source_state,
                "scheduling_state": issue.scheduling_state,
            },
        )
    )


def safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:1000]
