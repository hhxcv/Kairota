from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from kairota.contracts.enums import IssueSourceState, SchedulingState, SyncHealth
from kairota.contracts.schemas import (
    DependencyRead,
    IssueAnalysisCommand,
    IssueClaimCommand,
    IssuePageRead,
    IssueReleaseCommand,
    ManagedIssueRead,
)
from kairota.models.records import (
    AuditEvent,
    IssueDependency,
    ManagedIssue,
    Project,
    ProjectSyncState,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command


def list_issues(
    session: Session,
    *,
    project_ids: tuple[str, ...] = (),
    states: tuple[SchedulingState, ...] = (),
    query: str | None = None,
    claimable: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    sync_stale_after_seconds: int = 300,
) -> IssuePageRead:
    projects = {
        project.id: project for project in session.scalars(select(Project))
    }
    statement = select(ManagedIssue)
    if project_ids:
        statement = statement.where(ManagedIssue.project_id.in_(project_ids))
    issues = list(session.scalars(statement))
    normalized_query = (query or "").strip().lower()
    if normalized_query:
        issues = [
            issue
            for issue in issues
            if normalized_query in issue.title.lower()
            or normalized_query in str(issue.number)
            or normalized_query in projects[issue.project_id].name.lower()
        ]

    state_counts = Counter(issue.scheduling_state for issue in issues)
    reads = [
        issue_to_read(
            session,
            issue,
            sync_stale_after_seconds=sync_stale_after_seconds,
        )
        for issue in issues
    ]
    if states:
        requested_states = {state.value for state in states}
        reads = [
            item for item in reads if str(item.scheduling_state) in requested_states
        ]
    if claimable is not None:
        reads = [item for item in reads if item.claimable_now is claimable]
    reads.sort(key=lambda item: (projects[item.project_id].name, item.number, item.id))
    total = len(reads)
    start = (page - 1) * page_size
    return IssuePageRead(
        items=tuple(reads[start : start + page_size]),
        total=total,
        page=page,
        page_size=page_size,
        by_state={state.value: state_counts[state.value] for state in SchedulingState},
    )


def get_issue_read(
    session: Session,
    issue_id: str,
    *,
    sync_stale_after_seconds: int = 300,
) -> ManagedIssueRead | None:
    issue = session.get(ManagedIssue, issue_id)
    if issue is None:
        return None
    return issue_to_read(
        session,
        issue,
        sync_stale_after_seconds=sync_stale_after_seconds,
    )


def analyze_issue_command(
    session: Session,
    *,
    issue_id: str,
    command: IssueAnalysisCommand,
    idempotency_key: str,
    actor: str = "main-ai",
    sync_stale_after_seconds: int = 300,
) -> ManagedIssueRead:
    payload: JsonObject = {
        "issue_id": issue_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        issue = require_issue(session, issue_id)
        if issue.scheduling_state == SchedulingState.IN_PROGRESS.value:
            raise CommandBlockedError(
                "issue_in_progress",
                "Release the Issue before replacing its dependency analysis.",
            )
        if issue.source_state == IssueSourceState.CLOSED.value:
            raise CommandBlockedError(
                "issue_closed", "Closed Issues cannot be analyzed."
            )
        if issue.analysis_version != command.expected_analysis_version:
            raise CommandBlockedError(
                "analysis_version_conflict",
                "Issue analysis changed since it was read.",
                {"current_analysis_version": issue.analysis_version},
            )
        dependencies = dependency_targets(
            session,
            project_id=issue.project_id,
            issue_id=issue.id,
            numbers=command.dependency_issue_numbers,
        )
        validate_acyclic_replacement(
            session, issue.id, tuple(dep.id for dep in dependencies)
        )
        session.execute(
            delete(IssueDependency).where(IssueDependency.issue_id == issue.id)
        )
        session.add_all(
            IssueDependency(issue_id=issue.id, depends_on_issue_id=dependency.id)
            for dependency in dependencies
        )
        issue.manual_hold_reason = normalize_optional_text(command.manual_hold_reason)
        issue.analysis_completed = True
        issue.analysis_version += 1
        recompute_issue_state(session, issue)
        session.add(
            AuditEvent(
                actor=actor,
                action="analyze_issue",
                issue_id=issue.id,
                summary="Replaced Issue dependency analysis.",
                details={
                    "dependency_numbers": sorted(command.dependency_issue_numbers),
                    "manual_hold": bool(issue.manual_hold_reason),
                },
            )
        )
        session.flush()
        read = issue_to_read(
            session, issue, sync_stale_after_seconds=sync_stale_after_seconds
        )
        return cast(JsonObject, read.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="issue.analyze",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ManagedIssueRead.model_validate(result.body)


def claim_issue_command(
    session: Session,
    *,
    issue_id: str,
    command: IssueClaimCommand,
    idempotency_key: str,
    actor: str = "main-ai",
    sync_stale_after_seconds: int = 300,
) -> ManagedIssueRead:
    payload: JsonObject = {
        "issue_id": issue_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        issue = require_issue(session, issue_id)
        recompute_issue_state(session, issue)
        block_reason = claim_block_reason(
            session,
            issue,
            sync_stale_after_seconds=sync_stale_after_seconds,
        )
        if block_reason is not None:
            raise CommandBlockedError(
                block_reason,
                "Issue is not currently claimable.",
                {"scheduling_state": issue.scheduling_state},
            )
        if issue.scheduling_version != command.expected_scheduling_version:
            raise CommandBlockedError(
                "scheduling_version_conflict",
                "Issue scheduling state changed since it was read.",
                {"current_scheduling_version": issue.scheduling_version},
            )
        now = datetime.now(UTC)
        claimed = cast(
            CursorResult[Any],
            session.execute(
                update(ManagedIssue)
                .where(
                    ManagedIssue.id == issue.id,
                    ManagedIssue.scheduling_state == SchedulingState.READY.value,
                    ManagedIssue.scheduling_version
                    == command.expected_scheduling_version,
                )
                .values(
                    scheduling_state=SchedulingState.IN_PROGRESS.value,
                    scheduling_version=ManagedIssue.scheduling_version + 1,
                    in_progress_since=now,
                )
            )
        )
        if claimed.rowcount != 1:
            raise CommandBlockedError(
                "claim_conflict",
                "Another request changed the Issue before this claim completed.",
            )
        session.add(
            AuditEvent(
                actor=actor,
                action="claim_issue",
                issue_id=issue.id,
                summary="Claimed Issue for main-AI dispatch.",
                details={},
            )
        )
        session.flush()
        refreshed = require_issue(session, issue.id, populate_existing=True)
        read = issue_to_read(
            session, refreshed, sync_stale_after_seconds=sync_stale_after_seconds
        )
        return cast(JsonObject, read.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="issue.claim",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ManagedIssueRead.model_validate(result.body)


def release_issue_command(
    session: Session,
    *,
    issue_id: str,
    command: IssueReleaseCommand,
    idempotency_key: str,
    actor: str = "main-ai",
    sync_stale_after_seconds: int = 300,
) -> ManagedIssueRead:
    payload: JsonObject = {
        "issue_id": issue_id,
        **cast(JsonObject, command.model_dump(mode="json")),
    }

    def execute() -> JsonObject:
        issue = require_issue(session, issue_id)
        if issue.scheduling_state != SchedulingState.IN_PROGRESS.value:
            raise CommandBlockedError(
                "issue_not_in_progress",
                "Only an in-progress Issue can be released.",
            )
        if issue.scheduling_version != command.expected_scheduling_version:
            raise CommandBlockedError(
                "scheduling_version_conflict",
                "Issue scheduling state changed since it was read.",
                {"current_scheduling_version": issue.scheduling_version},
            )
        invalidate_analysis(session, issue)
        session.add(
            AuditEvent(
                actor=actor,
                action="release_issue",
                issue_id=issue.id,
                summary="Released Issue for fresh dependency analysis.",
                details={"reason": command.reason},
            )
        )
        session.flush()
        read = issue_to_read(
            session, issue, sync_stale_after_seconds=sync_stale_after_seconds
        )
        return cast(JsonObject, read.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="issue.release",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    return ManagedIssueRead.model_validate(result.body)


def require_issue(
    session: Session, issue_id: str, *, populate_existing: bool = False
) -> ManagedIssue:
    issue = session.get(ManagedIssue, issue_id, populate_existing=populate_existing)
    if issue is None:
        raise CommandBlockedError(
            "issue_not_found", "Managed Issue does not exist.", {"issue_id": issue_id}
        )
    return issue


def recompute_issue_state(session: Session, issue: ManagedIssue) -> bool:
    if issue.source_state == IssueSourceState.CLOSED.value:
        target = SchedulingState.CLOSED.value
    elif issue.scheduling_state == SchedulingState.IN_PROGRESS.value:
        return False
    elif not issue.analysis_completed:
        target = SchedulingState.NEEDS_ANALYSIS.value
    elif issue.manual_hold_reason or has_open_dependencies(session, issue.id):
        target = SchedulingState.BLOCKED.value
    else:
        target = SchedulingState.READY.value
    if issue.scheduling_state == target:
        return False
    issue.scheduling_state = target
    issue.scheduling_version += 1
    if target != SchedulingState.IN_PROGRESS.value:
        issue.in_progress_since = None
    return True


def invalidate_analysis(session: Session, issue: ManagedIssue) -> None:
    session.execute(delete(IssueDependency).where(IssueDependency.issue_id == issue.id))
    issue.analysis_completed = False
    issue.analysis_version += 1
    issue.manual_hold_reason = None
    issue.scheduling_state = SchedulingState.NEEDS_ANALYSIS.value
    issue.scheduling_version += 1
    issue.in_progress_since = None


def recompute_dependents(session: Session, dependency_id: str) -> int:
    dependent_ids = tuple(
        session.scalars(
            select(IssueDependency.issue_id).where(
                IssueDependency.depends_on_issue_id == dependency_id
            )
        )
    )
    changed = 0
    for issue in session.scalars(
        select(ManagedIssue).where(ManagedIssue.id.in_(dependent_ids))
    ):
        changed += int(recompute_issue_state(session, issue))
    return changed


def issue_to_read(
    session: Session,
    issue: ManagedIssue,
    *,
    sync_stale_after_seconds: int,
) -> ManagedIssueRead:
    dependencies = dependency_reads(session, issue.id)
    reasons = blocking_reasons(issue, dependencies)
    block_reason = claim_block_reason(
        session,
        issue,
        sync_stale_after_seconds=sync_stale_after_seconds,
    )
    return ManagedIssueRead(
        id=issue.id,
        project_id=issue.project_id,
        number=issue.number,
        title=issue.title,
        url=issue.url,
        source_state=IssueSourceState(issue.source_state),
        scheduling_state=SchedulingState(issue.scheduling_state),
        scheduling_version=issue.scheduling_version,
        analysis_version=issue.analysis_version,
        analysis_completed=issue.analysis_completed,
        manual_hold_reason=issue.manual_hold_reason,
        in_progress_since=issue.in_progress_since,
        source_updated_at=issue.source_updated_at,
        last_synced_at=issue.last_synced_at,
        dependencies=dependencies,
        dependency_closed_count=sum(
            dependency.source_state == IssueSourceState.CLOSED
            for dependency in dependencies
        ),
        blocking_reasons=reasons,
        claimable_now=block_reason is None,
        claim_block_reason=block_reason,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


def claim_block_reason(
    session: Session,
    issue: ManagedIssue,
    *,
    sync_stale_after_seconds: int,
) -> str | None:
    if issue.scheduling_state != SchedulingState.READY.value:
        return f"state_{issue.scheduling_state}"
    project = session.get(Project, issue.project_id)
    if project is None or not project.enabled:
        return "project_disabled"
    sync_state = session.scalar(
        select(ProjectSyncState).where(ProjectSyncState.project_id == project.id)
    )
    if sync_state is None or sync_state.health != SyncHealth.HEALTHY.value:
        return "sync_unhealthy"
    if sync_state.last_success_at is None:
        return "sync_unknown"
    last_success = sync_state.last_success_at
    if last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=UTC)
    if datetime.now(UTC) - last_success > timedelta(seconds=sync_stale_after_seconds):
        return "sync_stale"
    return None


def dependency_reads(session: Session, issue_id: str) -> tuple[DependencyRead, ...]:
    dependencies = session.scalars(
        select(ManagedIssue)
        .join(
            IssueDependency,
            IssueDependency.depends_on_issue_id == ManagedIssue.id,
        )
        .where(IssueDependency.issue_id == issue_id)
        .order_by(ManagedIssue.number)
    )
    return tuple(
        DependencyRead(
            issue_id=dependency.id,
            number=dependency.number,
            title=dependency.title,
            source_state=IssueSourceState(dependency.source_state),
            url=dependency.url,
        )
        for dependency in dependencies
    )


def blocking_reasons(
    issue: ManagedIssue, dependencies: tuple[DependencyRead, ...]
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not issue.analysis_completed:
        reasons.append("analysis_required")
    if issue.manual_hold_reason:
        reasons.append("manual_hold")
    reasons.extend(
        f"dependency_open:{dependency.number}"
        for dependency in dependencies
        if dependency.source_state == IssueSourceState.OPEN
    )
    return tuple(reasons)


def has_open_dependencies(session: Session, issue_id: str) -> bool:
    return (
        session.scalar(
            select(ManagedIssue.id)
            .join(
                IssueDependency,
                IssueDependency.depends_on_issue_id == ManagedIssue.id,
            )
            .where(
                IssueDependency.issue_id == issue_id,
                ManagedIssue.source_state == IssueSourceState.OPEN.value,
            )
            .limit(1)
        )
        is not None
    )


def dependency_targets(
    session: Session,
    *,
    project_id: str,
    issue_id: str,
    numbers: tuple[int, ...],
) -> tuple[ManagedIssue, ...]:
    unique_numbers = tuple(sorted(set(numbers)))
    dependencies = tuple(
        session.scalars(
            select(ManagedIssue).where(
                ManagedIssue.project_id == project_id,
                ManagedIssue.number.in_(unique_numbers),
            )
        )
    )
    found_numbers = {dependency.number for dependency in dependencies}
    missing = tuple(number for number in unique_numbers if number not in found_numbers)
    if missing:
        raise CommandBlockedError(
            "dependency_not_found",
            "Every dependency must be a synced Issue in the same project.",
            {"issue_numbers": missing},
        )
    if any(dependency.id == issue_id for dependency in dependencies):
        raise CommandBlockedError("self_dependency", "Issue cannot depend on itself.")
    return dependencies


def validate_acyclic_replacement(
    session: Session, issue_id: str, dependency_ids: tuple[str, ...]
) -> None:
    graph: defaultdict[str, set[str]] = defaultdict(set)
    for current_issue_id, dependency_id in session.execute(
        select(IssueDependency.issue_id, IssueDependency.depends_on_issue_id).where(
            IssueDependency.issue_id != issue_id
        )
    ):
        graph[str(current_issue_id)].add(str(dependency_id))
    graph[issue_id] = set(dependency_ids)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CommandBlockedError(
                "dependency_cycle", "Dependency analysis would create a cycle."
            )
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in tuple(graph):
        visit(node)


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
