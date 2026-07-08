from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    CheckConclusion,
    CheckStatus,
    EventStatus,
    ReviewGateState,
    WorkItemStatus,
)
from kairota.contracts.schemas import (
    QueueWorkbenchEventRead,
    QueueWorkbenchRead,
    QueueWorkbenchRowRead,
    QueueWorkbenchRunRead,
    QueueWorkbenchSectionRead,
    WorkItemRead,
)
from kairota.models.records import (
    AuditEvent,
    InboundEvent,
    RepoCheckSummary,
    RepoPullRequest,
    RepoReviewSummary,
    SyncCursor,
    WorkerRun,
)
from kairota.services.idempotency import JsonObject
from kairota.services.work_items import list_work_items, queue_summary

SECTION_ORDER = ("ready", "running", "blocked", "waiting", "failed", "done")
SECTION_TITLES = {
    "ready": "Ready",
    "running": "Running",
    "blocked": "Blocked",
    "waiting": "Waiting",
    "failed": "Failed",
    "done": "Done",
}
STATUS_SECTION = {
    WorkItemStatus.READY: "ready",
    WorkItemStatus.CLAIMED: "running",
    WorkItemStatus.IMPLEMENTING: "running",
    WorkItemStatus.NEEDS_TRIAGE: "blocked",
    WorkItemStatus.BACKLOG: "blocked",
    WorkItemStatus.BLOCKED: "blocked",
    WorkItemStatus.HUMAN_DECISION: "blocked",
    WorkItemStatus.PR_OPEN: "waiting",
    WorkItemStatus.WAITING_CHECKS: "waiting",
    WorkItemStatus.MERGE_ARMED: "waiting",
    WorkItemStatus.STRICT_AI_REVIEW: "waiting",
    WorkItemStatus.CI_FAILED: "failed",
    WorkItemStatus.GATE_FAILED: "failed",
    WorkItemStatus.MERGED: "done",
    WorkItemStatus.DONE: "done",
}
DECISION_STATUSES = frozenset(
    {
        WorkItemStatus.NEEDS_TRIAGE,
        WorkItemStatus.BLOCKED,
        WorkItemStatus.HUMAN_DECISION,
        WorkItemStatus.STRICT_AI_REVIEW,
        WorkItemStatus.CI_FAILED,
        WorkItemStatus.GATE_FAILED,
    }
)
REASON_AND_ACTION = {
    WorkItemStatus.NEEDS_TRIAGE: (
        "needs_triage",
        "Triage scheduling facts",
    ),
    WorkItemStatus.BACKLOG: ("backlog", "Promote when ready"),
    WorkItemStatus.READY: ("ready_for_claim", "Run scheduler or claim"),
    WorkItemStatus.CLAIMED: ("lease_claimed", "Start worker run"),
    WorkItemStatus.IMPLEMENTING: ("worker_running", "Report progress"),
    WorkItemStatus.PR_OPEN: ("repository_pr_open", "Watch checks and review"),
    WorkItemStatus.WAITING_CHECKS: ("waiting_checks", "Wait for current-head checks"),
    WorkItemStatus.MERGE_ARMED: ("merge_armed", "Merge through repository gate"),
    WorkItemStatus.MERGED: ("merged", "Close worker run"),
    WorkItemStatus.DONE: ("done", "No action"),
    WorkItemStatus.BLOCKED: ("work_item_blocked", "Resolve blocker"),
    WorkItemStatus.HUMAN_DECISION: (
        "blocked_by_human_decision",
        "Capture decision",
    ),
    WorkItemStatus.STRICT_AI_REVIEW: (
        "blocked_by_review_gate",
        "Address review gate",
    ),
    WorkItemStatus.CI_FAILED: ("blocked_by_ci", "Repair failing checks"),
    WorkItemStatus.GATE_FAILED: (
        "blocked_by_review_gate",
        "Repair repository gate",
    ),
}


def queue_workbench(session: Session) -> QueueWorkbenchRead:
    work_items = list_work_items(session)
    runs_by_work_item = latest_worker_runs_by_work_item(session)
    repository_by_work_item = repository_state_by_work_item(session)
    rows = tuple(
        work_item_to_row(
            work_item,
            worker_run=runs_by_work_item.get(work_item.id),
            repository=repository_by_work_item.get(work_item.id, {}),
        )
        for work_item in work_items
    )
    rows_by_section: defaultdict[str, list[QueueWorkbenchRowRead]] = defaultdict(list)
    for row in rows:
        rows_by_section[row.section].append(row)

    return QueueWorkbenchRead(
        summary=queue_summary(session),
        sections=tuple(
            QueueWorkbenchSectionRead(
                id=section_id,
                title=SECTION_TITLES[section_id],
                count=len(rows_by_section[section_id]),
                rows=tuple(rows_by_section[section_id]),
            )
            for section_id in SECTION_ORDER
        ),
        decision_inbox=tuple(
            row for row in rows if WorkItemStatus(str(row.status)) in DECISION_STATUSES
        ),
        recent_events=recent_audit_events(session),
        failures=recent_failures(session),
    )


def work_item_to_row(
    work_item: WorkItemRead,
    *,
    worker_run: WorkerRun | None,
    repository: JsonObject,
) -> QueueWorkbenchRowRead:
    status = WorkItemStatus(str(work_item.status))
    reason_code, next_action = REASON_AND_ACTION[status]
    return QueueWorkbenchRowRead(
        id=work_item.id,
        title=work_item.title,
        section=STATUS_SECTION[status],
        status=status,
        priority=work_item.priority,
        risk=work_item.risk,
        work_type=work_item.work_type,
        autonomy_mode=work_item.autonomy_mode,
        expected_touch=work_item.expected_touch,
        acceptance=work_item.acceptance,
        validation=work_item.validation,
        source_url=work_item.source_url,
        conflict_keys=work_item.conflict_keys,
        dependency_ids=work_item.dependency_ids,
        reason_code=reason_code,
        next_action=next_action,
        worker_run=worker_run_to_read(worker_run) if worker_run is not None else None,
        repository=repository,
    )


def latest_worker_runs_by_work_item(session: Session) -> dict[str, WorkerRun]:
    runs_by_work_item: dict[str, WorkerRun] = {}
    worker_runs = session.scalars(
        select(WorkerRun).order_by(
            WorkerRun.created_at.desc(),
            WorkerRun.id.desc(),
        )
    )
    for run in worker_runs:
        runs_by_work_item.setdefault(run.work_item_id, run)
    return runs_by_work_item


def repository_state_by_work_item(session: Session) -> dict[str, JsonObject]:
    pull_requests_by_work_item: dict[str, RepoPullRequest] = {}
    pull_requests = session.scalars(
        select(RepoPullRequest)
        .where(RepoPullRequest.work_item_id.is_not(None))
        .order_by(RepoPullRequest.updated_at.desc(), RepoPullRequest.id.desc())
    )
    for pull_request in pull_requests:
        if pull_request.work_item_id is not None:
            pull_requests_by_work_item.setdefault(
                pull_request.work_item_id,
                pull_request,
            )

    reviews_by_pr_id = {
        review.pull_request_id: review
        for review in session.scalars(select(RepoReviewSummary))
    }
    checks_by_pr_id: defaultdict[str, list[RepoCheckSummary]] = defaultdict(list)
    for check in session.scalars(select(RepoCheckSummary)):
        checks_by_pr_id[check.pull_request_id].append(check)

    return {
        work_item_id: pull_request_state(
            pull_request,
            checks=checks_by_pr_id[pull_request.id],
            review=reviews_by_pr_id.get(pull_request.id),
        )
        for work_item_id, pull_request in pull_requests_by_work_item.items()
    }


def pull_request_state(
    pull_request: RepoPullRequest,
    *,
    checks: list[RepoCheckSummary],
    review: RepoReviewSummary | None,
) -> JsonObject:
    current_checks = [check for check in checks if not check.stale]
    failing_checks = [
        check
        for check in current_checks
        if check.conclusion
        in {
            CheckConclusion.FAILURE.value,
            CheckConclusion.TIMED_OUT.value,
            CheckConclusion.ACTION_REQUIRED.value,
        }
    ]
    pending_checks = [
        check for check in current_checks if check.status != CheckStatus.COMPLETED.value
    ]
    return {
        "pull_request_number": pull_request.number,
        "pull_request_state": pull_request.state,
        "draft": pull_request.draft,
        "merged": pull_request.merged,
        "head_sha": pull_request.head_sha,
        "current_checks": len(current_checks),
        "failing_checks": len(failing_checks),
        "pending_checks": len(pending_checks),
        "review_state": review.state
        if review is not None
        else ReviewGateState.UNKNOWN.value,
        "unresolved_threads": review.unresolved_count if review is not None else 0,
    }


def worker_run_to_read(run: WorkerRun) -> QueueWorkbenchRunRead:
    return QueueWorkbenchRunRead(
        id=run.id,
        lease_id=run.lease_id,
        role=run.role,
        status=run.status,
        result=run.result,
        heartbeat_at=run.heartbeat_at,
        closed_at=run.closed_at,
    )


def recent_audit_events(
    session: Session,
    *,
    limit: int = 12,
) -> tuple[QueueWorkbenchEventRead, ...]:
    events = session.scalars(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return tuple(
        QueueWorkbenchEventRead(
            id=event.id,
            kind="audit",
            summary=event.summary,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            status="recorded",
            created_at=event.created_at,
            details=event.details,
        )
        for event in events
    )


def recent_failures(
    session: Session,
    *,
    limit: int = 8,
) -> tuple[QueueWorkbenchEventRead, ...]:
    failures: list[QueueWorkbenchEventRead] = []
    inbound_events = session.scalars(
        select(InboundEvent)
        .where(InboundEvent.status == EventStatus.FAILED.value)
        .order_by(InboundEvent.created_at.desc(), InboundEvent.id.desc())
        .limit(limit)
    )
    for event in inbound_events:
        failures.append(
            QueueWorkbenchEventRead(
                id=event.id,
                kind="inbound_event",
                summary=f"{event.event_type} failed",
                subject_type="inbound_event",
                subject_id=event.id,
                status=event.status,
                created_at=event.created_at,
                details={
                    "provider": event.provider,
                    "event_type": event.event_type,
                    "action": event.action,
                },
            )
        )

    sync_cursors = session.scalars(
        select(SyncCursor)
        .where(SyncCursor.last_failure_at.is_not(None))
        .order_by(SyncCursor.last_failure_at.desc(), SyncCursor.id.desc())
        .limit(limit)
    )
    for cursor in sync_cursors:
        failures.append(
            QueueWorkbenchEventRead(
                id=cursor.id,
                kind="sync_cursor",
                summary="Repository sync failed",
                subject_type="sync_cursor",
                subject_id=cursor.id,
                status="failed",
                created_at=cursor.last_failure_at,
                details={
                    "provider": cursor.provider,
                    "repository_id": cursor.repository_id,
                    "sync_kind": cursor.sync_kind,
                },
            )
        )

    return tuple(
        sorted(
            failures,
            key=lambda failure: (failure.created_at is not None, failure.created_at),
            reverse=True,
        )[:limit]
    )
