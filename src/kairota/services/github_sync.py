from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kairota.adapters.github.models import (
    GitHubCheckSnapshot,
    GitHubClient,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubRepositoryConfig,
    GitHubRepositorySnapshot,
    GitHubReviewSnapshot,
    GitHubSyncSnapshot,
    GitHubWebhookEvent,
)
from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    EventStatus,
    PullRequestState,
    RepositoryProvider,
    ReviewGateState,
    WorkItemStatus,
)
from kairota.contracts.schemas import RepositorySyncRead
from kairota.domain.state_machine import is_work_item_transition_allowed
from kairota.models.records import (
    AuditEvent,
    ExternalRef,
    InboundEvent,
    RepoCheckSummary,
    RepoPullRequest,
    RepoReviewSummary,
    Repository,
    SyncCursor,
    WorkItem,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.idempotency import JsonObject, run_idempotent_command


@dataclass
class SyncStats:
    issues_seen: int = 0
    pull_requests_seen: int = 0
    checks_seen: int = 0
    reviews_seen: int = 0
    work_items_created: int = 0
    transitions_applied: int = 0
    stale_summaries_marked: int = 0


def sync_repository_command(
    session: Session,
    *,
    repository_id: str,
    idempotency_key: str,
    client: GitHubClient,
) -> RepositorySyncRead:
    payload: JsonObject = {"repository_id": repository_id}

    def execute() -> JsonObject:
        repository = session.get(Repository, repository_id)
        if repository is None:
            raise CommandBlockedError(
                "repository_not_found",
                "Repository does not exist.",
                {"repository_id": repository_id},
            )
        if repository.provider != RepositoryProvider.GITHUB.value:
            raise CommandBlockedError(
                "unsupported_provider",
                "Only GitHub repositories are supported in M1.5.",
                {"provider": repository.provider},
            )

        cursor = load_sync_cursor(session, repository.id, "poll")
        snapshot = client.fetch_repository_snapshot(
            repository_config(repository),
            cursor.cursor,
        )
        stats = apply_sync_snapshot(
            session,
            repository,
            snapshot,
            actor="github-sync",
            source="poll",
        )
        cursor.cursor = snapshot.next_cursor
        cursor.last_success_at = datetime.now(UTC)
        cursor.last_failure_at = None
        cursor.last_error = None
        repository.sync_status = "synced"
        read_model = sync_read(repository, stats, replayed=False)
        return cast(JsonObject, read_model.model_dump(mode="json"))

    result = run_idempotent_command(
        session,
        command_name="repository.sync",
        idempotency_key=idempotency_key,
        payload=payload,
        execute=execute,
    )
    body = dict(result.body)
    body["replayed"] = result.replayed
    return RepositorySyncRead.model_validate(body)


def process_github_webhook_event(
    session: Session,
    *,
    event: GitHubWebhookEvent,
) -> RepositorySyncRead:
    existing = session.scalar(
        select(InboundEvent)
        .where(
            InboundEvent.provider == RepositoryProvider.GITHUB.value,
            InboundEvent.idempotency_key == event.delivery_id,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.payload_hash != event.payload_hash:
            raise CommandBlockedError(
                "inbound_idempotency_conflict",
                "GitHub delivery id was reused with a different payload.",
                {"delivery_id": event.delivery_id},
            )
        repository = session.get(Repository, existing.repository_id)
        if repository is None:
            raise CommandBlockedError(
                "repository_not_found",
                "Inbound event references a repository that does not exist.",
                {"repository_id": existing.repository_id or ""},
            )
        return RepositorySyncRead(
            repository_id=repository.id,
            provider=RepositoryProvider.GITHUB,
            status="skipped",
            replayed=True,
            issues_seen=0,
            pull_requests_seen=0,
            checks_seen=0,
            reviews_seen=0,
            work_items_created=0,
            transitions_applied=0,
            stale_summaries_marked=0,
            inbound_event_id=existing.id,
        )

    repository = ensure_repository(session, event.snapshot.repository)
    inbound = InboundEvent(
        provider=RepositoryProvider.GITHUB.value,
        repository_id=repository.id,
        idempotency_key=event.delivery_id,
        event_type=event.event_type,
        action=event.action,
        external_id=event.external_id,
        payload_hash=event.payload_hash,
        status=EventStatus.PENDING.value,
    )
    session.add(inbound)
    session.flush()

    stats = SyncStats()
    try:
        with session.begin_nested():
            stats = apply_sync_snapshot(
                session,
                repository,
                event.snapshot,
                actor="github-webhook",
                source=f"webhook:{event.event_type}",
            )
        inbound.status = EventStatus.PROCESSED.value
        repository.sync_status = "synced"
        session.flush()
        return sync_read(
            repository,
            stats,
            replayed=False,
            inbound_event_id=inbound.id,
        )
    except CommandBlockedError as exc:
        inbound.status = EventStatus.FAILED.value
        inbound.error = exc.reason_code
        repository.sync_status = "failed"
        session.flush()
        return sync_read(
            repository,
            stats,
            replayed=False,
            inbound_event_id=inbound.id,
        )
    except Exception as exc:
        inbound.status = EventStatus.FAILED.value
        inbound.error = exc.__class__.__name__
        repository.sync_status = "failed"
        session.flush()
        return sync_read(
            repository,
            stats,
            replayed=False,
            inbound_event_id=inbound.id,
        )


def apply_sync_snapshot(
    session: Session,
    repository: Repository,
    snapshot: GitHubSyncSnapshot,
    *,
    actor: str,
    source: str,
) -> SyncStats:
    stats = SyncStats(
        issues_seen=len(snapshot.issues),
        pull_requests_seen=len(snapshot.pull_requests),
        checks_seen=len(snapshot.checks),
        reviews_seen=len(snapshot.reviews),
    )
    repository.provider_repo_id = snapshot.repository.provider_repo_id
    repository.name = snapshot.repository.name or repository.name
    repository.default_branch = snapshot.repository.default_branch

    for issue in snapshot.issues:
        work_item, created = upsert_issue(session, repository, issue, actor=actor)
        if created:
            stats.work_items_created += 1
        reduce_issue(session, repository, issue, work_item, stats, actor=actor)

    pr_records: dict[int, RepoPullRequest] = {}
    for pull_request in snapshot.pull_requests:
        pr_records[pull_request.number] = upsert_pull_request(
            session,
            repository,
            pull_request,
            stats,
            actor=actor,
        )

    for check in snapshot.checks:
        pr_record = pr_records.get(check.pull_request_number) or load_pr_by_number(
            session, repository.id, check.pull_request_number
        )
        if pr_record is not None:
            upsert_check(session, pr_record, check)

    for review in snapshot.reviews:
        pr_record = pr_records.get(review.pull_request_number) or load_pr_by_number(
            session, repository.id, review.pull_request_number
        )
        if pr_record is not None:
            upsert_review(session, pr_record, review)

    for pr_record in pr_records.values():
        reduce_pull_request(session, pr_record, stats, actor=actor, source=source)

    session.flush()
    return stats


def upsert_issue(
    session: Session,
    repository: Repository,
    issue: GitHubIssueSnapshot,
    *,
    actor: str,
) -> tuple[WorkItem, bool]:
    external_id = issue_external_id(repository.id, issue.number)
    external_ref = session.scalar(
        select(ExternalRef).where(
            ExternalRef.provider == RepositoryProvider.GITHUB.value,
            ExternalRef.external_type == "issue",
            ExternalRef.external_id == external_id,
        )
    )
    if external_ref and external_ref.work_item_id:
        work_item = session.get(WorkItem, external_ref.work_item_id)
        if work_item is None:
            raise CommandBlockedError(
                "missing_work_item",
                "Issue external reference points to a missing work item.",
                {"external_id": external_id},
            )
        if work_item.status in {
            WorkItemStatus.NEEDS_TRIAGE.value,
            WorkItemStatus.BACKLOG.value,
        }:
            work_item.title = issue.title
        work_item.source_url = issue.url
        work_item.repository_id = repository.id
        external_ref.repository_id = repository.id
        return work_item, False

    work_item = WorkItem(
        title=issue.title,
        repository_id=repository.id,
        status=WorkItemStatus.NEEDS_TRIAGE.value,
        priority=100,
        risk="medium",
        work_type="implementation",
        autonomy_mode="ai_assisted",
        source_url=issue.url,
    )
    session.add(work_item)
    session.flush()
    session.add(
        ExternalRef(
            provider=RepositoryProvider.GITHUB.value,
            external_type="issue",
            external_id=external_id,
            url=issue.url,
            work_item_id=work_item.id,
            repository_id=repository.id,
        )
    )
    audit(
        session,
        actor=actor,
        action="sync_issue_create_work_item",
        subject_type="work_item",
        subject_id=work_item.id,
        summary="Created work item from GitHub issue summary.",
        details={"repository_id": repository.id, "issue_number": issue.number},
    )
    return work_item, True


def reduce_issue(
    session: Session,
    repository: Repository,
    issue: GitHubIssueSnapshot,
    work_item: WorkItem,
    stats: SyncStats,
    *,
    actor: str,
) -> None:
    if issue.state != "closed":
        return
    merged_pr_exists = session.scalar(
        select(RepoPullRequest.id)
        .where(
            RepoPullRequest.repository_id == repository.id,
            RepoPullRequest.work_item_id == work_item.id,
            RepoPullRequest.merged.is_(True),
        )
        .limit(1)
    )
    if not merged_pr_exists:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.HUMAN_DECISION,
            stats,
            actor=actor,
            reason="issue_closed_without_merged_pr",
        )


def upsert_pull_request(
    session: Session,
    repository: Repository,
    pull_request: GitHubPullRequestSnapshot,
    stats: SyncStats,
    *,
    actor: str,
) -> RepoPullRequest:
    record = session.scalar(
        select(RepoPullRequest).where(
            RepoPullRequest.repository_id == repository.id,
            RepoPullRequest.provider_pr_id == str(pull_request.number),
        )
    )
    linked_work_item_id = linked_work_item_id_for_pr(session, repository, pull_request)
    if record is None:
        record = RepoPullRequest(
            repository_id=repository.id,
            provider_pr_id=str(pull_request.number),
            number=pull_request.number,
            url=pull_request.url,
            state=pull_request.state.value,
            draft=pull_request.draft,
            head_branch=pull_request.head_branch,
            head_sha=pull_request.head_sha,
            merged=pull_request.merged,
            merge_commit_sha=pull_request.merge_commit_sha,
            work_item_id=linked_work_item_id,
            stale=False,
        )
        session.add(record)
        session.flush()
    else:
        if (
            record.head_sha
            and pull_request.head_sha
            and record.head_sha != pull_request.head_sha
        ):
            stats.stale_summaries_marked += mark_stale_pr_summaries(session, record.id)
        record.url = pull_request.url
        record.state = pull_request.state.value
        record.draft = pull_request.draft
        record.head_branch = pull_request.head_branch
        record.head_sha = pull_request.head_sha
        record.merged = pull_request.merged
        record.merge_commit_sha = pull_request.merge_commit_sha
        if linked_work_item_id:
            record.work_item_id = linked_work_item_id
        record.stale = False

    if record.work_item_id:
        audit(
            session,
            actor=actor,
            action="sync_pull_request_summary",
            subject_type="repo_pull_request",
            subject_id=record.id,
            summary="Updated GitHub pull request summary.",
            details={
                "number": record.number,
                "state": record.state,
                "work_item_id": record.work_item_id,
            },
        )
    return record


def upsert_check(
    session: Session,
    pull_request: RepoPullRequest,
    check: GitHubCheckSnapshot,
) -> RepoCheckSummary:
    record = session.scalar(
        select(RepoCheckSummary).where(
            RepoCheckSummary.pull_request_id == pull_request.id,
            RepoCheckSummary.name == check.name,
            RepoCheckSummary.head_sha == check.head_sha,
        )
    )
    stale = bool(
        check.head_sha
        and pull_request.head_sha
        and check.head_sha != pull_request.head_sha
    )
    if record is None:
        record = RepoCheckSummary(
            pull_request_id=pull_request.id,
            name=check.name,
            status=check.status.value,
            conclusion=check.conclusion.value,
            head_sha=check.head_sha,
            required=check.required,
            stale=stale,
            details_url=check.details_url,
        )
        session.add(record)
    else:
        record.status = check.status.value
        record.conclusion = check.conclusion.value
        record.required = check.required
        record.stale = stale
        record.details_url = check.details_url
    return record


def upsert_review(
    session: Session,
    pull_request: RepoPullRequest,
    review: GitHubReviewSnapshot,
) -> RepoReviewSummary:
    record = session.scalar(
        select(RepoReviewSummary).where(
            RepoReviewSummary.pull_request_id == pull_request.id
        )
    )
    stale = bool(
        review.head_sha
        and pull_request.head_sha
        and review.head_sha != pull_request.head_sha
    )
    if record is None:
        record = RepoReviewSummary(
            pull_request_id=pull_request.id,
            state=review.state.value,
            unresolved_count=review.unresolved_count,
            stale=stale,
            summary=review.summary,
        )
        session.add(record)
    else:
        record.state = review.state.value
        record.unresolved_count = review.unresolved_count
        record.stale = stale
        record.summary = review.summary
    return record


def reduce_pull_request(
    session: Session,
    pull_request: RepoPullRequest,
    stats: SyncStats,
    *,
    actor: str,
    source: str,
) -> None:
    if not pull_request.work_item_id:
        return
    work_item = session.get(WorkItem, pull_request.work_item_id)
    if work_item is None:
        return

    if pull_request.merged or pull_request.state == PullRequestState.MERGED.value:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.MERGED,
            stats,
            actor=actor,
            reason="pull_request_merged",
        )
        return

    if pull_request.state == PullRequestState.CLOSED.value:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.HUMAN_DECISION,
            stats,
            actor=actor,
            reason="pull_request_closed_unmerged",
        )
        return

    if work_item.status == WorkItemStatus.IMPLEMENTING.value:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.PR_OPEN,
            stats,
            actor=actor,
            reason="pull_request_open",
        )

    apply_gate_reducer(
        session, pull_request, work_item, stats, actor=actor, source=source
    )


def apply_gate_reducer(
    session: Session,
    pull_request: RepoPullRequest,
    work_item: WorkItem,
    stats: SyncStats,
    *,
    actor: str,
    source: str,
) -> None:
    if work_item.status not in {
        WorkItemStatus.PR_OPEN.value,
        WorkItemStatus.WAITING_CHECKS.value,
        WorkItemStatus.CI_FAILED.value,
        WorkItemStatus.STRICT_AI_REVIEW.value,
        WorkItemStatus.GATE_FAILED.value,
        WorkItemStatus.MERGE_ARMED.value,
    }:
        return

    current_checks = tuple(
        session.scalars(
            select(RepoCheckSummary).where(
                RepoCheckSummary.pull_request_id == pull_request.id,
                RepoCheckSummary.stale.is_(False),
                RepoCheckSummary.head_sha == pull_request.head_sha,
            )
        )
    )
    required_checks = tuple(check for check in current_checks if check.required)
    failed_checks = tuple(
        check
        for check in required_checks
        if check.conclusion
        in {
            CheckConclusion.FAILURE.value,
            CheckConclusion.CANCELLED.value,
            CheckConclusion.TIMED_OUT.value,
            CheckConclusion.ACTION_REQUIRED.value,
        }
    )
    pending_checks = tuple(
        check
        for check in required_checks
        if check.status != CheckStatus.COMPLETED.value
        or check.conclusion == CheckConclusion.UNKNOWN.value
    )
    if failed_checks:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.CI_FAILED,
            stats,
            actor=actor,
            reason="required_check_failed",
        )
        return
    if pending_checks:
        transition_work_item(
            session,
            work_item,
            gate_regression_target(work_item, WorkItemStatus.WAITING_CHECKS),
            stats,
            actor=actor,
            reason="required_check_pending",
        )
        return

    review = session.scalar(
        select(RepoReviewSummary).where(
            RepoReviewSummary.pull_request_id == pull_request.id,
            RepoReviewSummary.stale.is_(False),
        )
    )
    if review is None or review.state in {
        ReviewGateState.UNKNOWN.value,
        ReviewGateState.WAITING.value,
    }:
        if work_item.status == WorkItemStatus.MERGE_ARMED.value:
            transition_work_item(
                session,
                work_item,
                WorkItemStatus.PR_OPEN,
                stats,
                actor=actor,
                reason="review_gate_incomplete_after_merge_armed",
            )
        audit(
            session,
            actor=actor,
            action="review_gate_incomplete",
            subject_type="work_item",
            subject_id=work_item.id,
            summary="Review gate is incomplete for current pull request head.",
            details={"pull_request_id": pull_request.id, "source": source},
        )
        return
    if review.state in {
        ReviewGateState.CHANGES_REQUESTED.value,
        ReviewGateState.UNRESOLVED_THREADS.value,
    }:
        transition_work_item(
            session,
            work_item,
            WorkItemStatus.STRICT_AI_REVIEW,
            stats,
            actor=actor,
            reason="review_gate_failed",
        )
        return

    transition_work_item(
        session,
        work_item,
        WorkItemStatus.MERGE_ARMED,
        stats,
        actor=actor,
        reason="checks_and_review_passed",
    )


def gate_regression_target(
    work_item: WorkItem,
    desired: WorkItemStatus,
) -> WorkItemStatus:
    if (
        work_item.status == WorkItemStatus.MERGE_ARMED.value
        and desired == WorkItemStatus.WAITING_CHECKS
    ):
        return WorkItemStatus.PR_OPEN
    return desired


def transition_work_item(
    session: Session,
    work_item: WorkItem,
    target: WorkItemStatus,
    stats: SyncStats,
    *,
    actor: str,
    reason: str,
) -> None:
    current = WorkItemStatus(work_item.status)
    if current == target:
        return
    if not is_work_item_transition_allowed(current, target):
        audit(
            session,
            actor=actor,
            action="blocked_repository_transition",
            subject_type="work_item",
            subject_id=work_item.id,
            summary="Repository reducer did not apply a disallowed transition.",
            details={"from": current.value, "to": target.value, "reason": reason},
        )
        return
    work_item.status = target.value
    stats.transitions_applied += 1
    audit(
        session,
        actor=actor,
        action="repository_transition",
        subject_type="work_item",
        subject_id=work_item.id,
        summary="Applied repository-derived work item transition.",
        details={"from": current.value, "to": target.value, "reason": reason},
    )


def mark_stale_pr_summaries(session: Session, pull_request_id: str) -> int:
    count = 0
    checks = tuple(
        session.scalars(
            select(RepoCheckSummary).where(
                RepoCheckSummary.pull_request_id == pull_request_id,
                RepoCheckSummary.stale.is_(False),
            )
        )
    )
    for check in checks:
        check.stale = True
        count += 1

    review = session.scalar(
        select(RepoReviewSummary).where(
            RepoReviewSummary.pull_request_id == pull_request_id,
            RepoReviewSummary.stale.is_(False),
        )
    )
    if review is not None:
        review.stale = True
        count += 1
    return count


def linked_work_item_id_for_pr(
    session: Session,
    repository: Repository,
    pull_request: GitHubPullRequestSnapshot,
) -> str | None:
    for issue_number in pull_request.linked_issue_numbers:
        ref = session.scalar(
            select(ExternalRef).where(
                ExternalRef.provider == RepositoryProvider.GITHUB.value,
                ExternalRef.external_type == "issue",
                ExternalRef.external_id
                == issue_external_id(repository.id, issue_number),
            )
        )
        if ref and ref.work_item_id:
            return ref.work_item_id
    return None


def ensure_repository(
    session: Session,
    snapshot: GitHubRepositorySnapshot,
) -> Repository:
    repository = session.scalar(
        select(Repository).where(
            Repository.provider == RepositoryProvider.GITHUB.value,
            Repository.provider_repo_id == snapshot.provider_repo_id,
        )
    )
    if repository is None:
        repository = session.scalar(
            select(Repository).where(
                Repository.provider == RepositoryProvider.GITHUB.value,
                Repository.name == snapshot.name,
            )
        )
    if repository is None:
        repository = Repository(
            provider=RepositoryProvider.GITHUB.value,
            provider_repo_id=snapshot.provider_repo_id,
            name=snapshot.name,
            default_branch=snapshot.default_branch,
            sync_status="unknown",
        )
        session.add(repository)
        try:
            session.flush()
        except IntegrityError as exc:
            raise CommandBlockedError(
                "repository_conflict",
                "Repository could not be created from GitHub event.",
                {"provider_repo_id": snapshot.provider_repo_id},
            ) from exc
    else:
        repository.provider_repo_id = snapshot.provider_repo_id
        repository.name = snapshot.name
        repository.default_branch = snapshot.default_branch
    return repository


def load_pr_by_number(
    session: Session,
    repository_id: str,
    number: int,
) -> RepoPullRequest | None:
    return session.scalar(
        select(RepoPullRequest).where(
            RepoPullRequest.repository_id == repository_id,
            RepoPullRequest.number == number,
        )
    )


def load_sync_cursor(
    session: Session,
    repository_id: str,
    sync_kind: str,
) -> SyncCursor:
    cursor = session.scalar(
        select(SyncCursor).where(
            SyncCursor.provider == RepositoryProvider.GITHUB.value,
            SyncCursor.repository_id == repository_id,
            SyncCursor.sync_kind == sync_kind,
        )
    )
    if cursor is None:
        cursor = SyncCursor(
            provider=RepositoryProvider.GITHUB.value,
            repository_id=repository_id,
            sync_kind=sync_kind,
        )
        session.add(cursor)
        session.flush()
    return cursor


def repository_config(repository: Repository) -> GitHubRepositoryConfig:
    owner, name = split_repo_name(repository.name)
    return GitHubRepositoryConfig(
        owner=owner,
        name=name,
        provider_repo_id=repository.provider_repo_id,
    )


def split_repo_name(full_name: str) -> tuple[str, str]:
    if "/" not in full_name:
        raise CommandBlockedError(
            "invalid_repository_name",
            "GitHub repository name must use owner/name.",
            {"name": full_name},
        )
    owner, name = full_name.split("/", 1)
    if not owner or not name:
        raise CommandBlockedError(
            "invalid_repository_name",
            "GitHub repository name must use owner/name.",
            {"name": full_name},
        )
    return owner, name


def issue_external_id(repository_id: str, issue_number: int) -> str:
    return f"{repository_id}#issue:{issue_number}"


def audit(
    session: Session,
    *,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str | None,
    summary: str,
    details: JsonObject,
) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            summary=summary,
            details=details,
        )
    )


def sync_read(
    repository: Repository,
    stats: SyncStats,
    *,
    replayed: bool,
    inbound_event_id: str | None = None,
) -> RepositorySyncRead:
    return RepositorySyncRead(
        repository_id=repository.id,
        provider=RepositoryProvider.GITHUB,
        status=repository.sync_status,
        replayed=replayed,
        issues_seen=stats.issues_seen,
        pull_requests_seen=stats.pull_requests_seen,
        checks_seen=stats.checks_seen,
        reviews_seen=stats.reviews_seen,
        work_items_created=stats.work_items_created,
        transitions_applied=stats.transitions_applied,
        stale_summaries_marked=stats.stale_summaries_marked,
        inbound_event_id=inbound_event_id,
    )
