from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.contracts.enums import (
    AutonomyMode,
    CheckConclusion,
    CheckStatus,
    EventStatus,
    LeaseStatus,
    RepositoryProvider,
    ReviewGateState,
    RiskLevel,
    WorkerRole,
    WorkerRunStatus,
    WorkItemStatus,
    WorkType,
)
from kairota.contracts.schemas import DemoSeedRead
from kairota.models.records import (
    AuditEvent,
    InboundEvent,
    Lease,
    LockHolder,
    RepoCheckSummary,
    RepoPullRequest,
    RepoReviewSummary,
    Repository,
    SyncCursor,
    WorkerRun,
    WorkItem,
    WorkItemConflictKey,
    WorkItemDependency,
)

DEMO_REPOSITORY_ID = "m1-demo-repository"


class DemoWorkItem(TypedDict):
    id: str
    title: str
    status: WorkItemStatus
    priority: int
    risk: RiskLevel
    work_type: WorkType
    autonomy_mode: AutonomyMode
    expected_touch: str
    acceptance: str
    validation: str
    conflict_keys: tuple[str, ...]
    dependency_ids: tuple[str, ...]


DEMO_WORK_ITEMS: tuple[DemoWorkItem, ...] = (
    {
        "id": "m1-demo-ready",
        "title": "M1 demo ready work",
        "status": WorkItemStatus.READY,
        "priority": 10,
        "risk": RiskLevel.MEDIUM,
        "work_type": WorkType.IMPLEMENTATION,
        "autonomy_mode": AutonomyMode.AI_ASSISTED,
        "expected_touch": "src/kairota/services/demo_data.py",
        "acceptance": "Ready work can be scheduled and claimed.",
        "validation": "Run M1 exit smoke.",
        "conflict_keys": ("runtime:demo-ready",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-running",
        "title": "M1 demo running worker",
        "status": WorkItemStatus.IMPLEMENTING,
        "priority": 20,
        "risk": RiskLevel.HIGH,
        "work_type": WorkType.IMPLEMENTATION,
        "autonomy_mode": AutonomyMode.FULLY_AUTONOMOUS,
        "expected_touch": "src/kairota/services/worker_runs.py",
        "acceptance": "Worker run is visible with lease authority.",
        "validation": "Worker run lifecycle tests.",
        "conflict_keys": ("runtime:worker",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-stale-lease",
        "title": "M1 demo stale lease recovery",
        "status": WorkItemStatus.CLAIMED,
        "priority": 25,
        "risk": RiskLevel.HIGH,
        "work_type": WorkType.OPERATIONS,
        "autonomy_mode": AutonomyMode.AI_ASSISTED,
        "expected_touch": "src/kairota/scheduler/claims.py",
        "acceptance": "Expired active lease is visible as a recovery signal.",
        "validation": "Run lease reconciliation.",
        "conflict_keys": ("runtime:lease-recovery",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-blocked",
        "title": "M1 demo human decision",
        "status": WorkItemStatus.HUMAN_DECISION,
        "priority": 30,
        "risk": RiskLevel.MEDIUM,
        "work_type": WorkType.DESIGN,
        "autonomy_mode": AutonomyMode.HUMAN_REQUIRED,
        "expected_touch": "docs/architecture/m1-ai-dev-queue.md",
        "acceptance": "Decision owner is explicit before scheduling resumes.",
        "validation": "Governance check.",
        "conflict_keys": ("governance:decision",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-waiting",
        "title": "M1 demo waiting checks",
        "status": WorkItemStatus.WAITING_CHECKS,
        "priority": 40,
        "risk": RiskLevel.MEDIUM,
        "work_type": WorkType.IMPLEMENTATION,
        "autonomy_mode": AutonomyMode.AI_ASSISTED,
        "expected_touch": "src/kairota/adapters/github/**",
        "acceptance": "Current-head checks are visible before merge.",
        "validation": "GitHub sync tests.",
        "conflict_keys": ("adapter:github",),
        "dependency_ids": ("m1-demo-ready",),
    },
    {
        "id": "m1-demo-review",
        "title": "M1 demo strict AI review",
        "status": WorkItemStatus.STRICT_AI_REVIEW,
        "priority": 45,
        "risk": RiskLevel.HIGH,
        "work_type": WorkType.TEST,
        "autonomy_mode": AutonomyMode.AI_ASSISTED,
        "expected_touch": "tests/test_github_sync.py",
        "acceptance": "Review blockers prevent merge arming.",
        "validation": "Review gate tests.",
        "conflict_keys": ("adapter:github",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-failed",
        "title": "M1 demo failed CI",
        "status": WorkItemStatus.CI_FAILED,
        "priority": 50,
        "risk": RiskLevel.HIGH,
        "work_type": WorkType.TEST,
        "autonomy_mode": AutonomyMode.AI_ASSISTED,
        "expected_touch": "tests/test_github_sync.py",
        "acceptance": "Failed checks remain visible until repaired.",
        "validation": "Check reducer tests.",
        "conflict_keys": ("adapter:github",),
        "dependency_ids": (),
    },
    {
        "id": "m1-demo-done",
        "title": "M1 demo completed work",
        "status": WorkItemStatus.DONE,
        "priority": 60,
        "risk": RiskLevel.MEDIUM,
        "work_type": WorkType.IMPLEMENTATION,
        "autonomy_mode": AutonomyMode.FULLY_AUTONOMOUS,
        "expected_touch": "src/kairota/services/worker_runs.py",
        "acceptance": "Merged and closed work remains auditable.",
        "validation": "M1 exit smoke.",
        "conflict_keys": ("runtime:worker",),
        "dependency_ids": (),
    },
)


def seed_m1_demo_data(session: Session) -> DemoSeedRead:
    now = datetime.now(UTC)
    seeded_records = 0
    for item in DEMO_WORK_ITEMS:
        seeded_records += ensure_work_item(session, item)
        seeded_records += ensure_conflict_keys(
            session,
            work_item_id=str(item["id"]),
            conflict_keys=tuple(str(key) for key in item["conflict_keys"]),
        )
        seeded_records += ensure_dependencies(
            session,
            work_item_id=str(item["id"]),
            dependency_ids=tuple(str(dep) for dep in item["dependency_ids"]),
        )

    seeded_records += ensure_demo_worker_state(session, now=now)
    seeded_records += ensure_demo_repository_state(session, now=now)
    seeded_records += ensure_audit_event(
        session,
        event_id="m1-demo-audit-ready",
        actor="demo",
        action="seed_m1_demo_data",
        subject_type="work_item",
        subject_id="m1-demo-ready",
        summary="M1 demo data seeded.",
        details={"scope": "m1-exit"},
    )
    session.flush()
    return DemoSeedRead(
        status="seeded",
        work_item_ids=tuple(str(item["id"]) for item in DEMO_WORK_ITEMS),
        repository_ids=(DEMO_REPOSITORY_ID,),
        seeded_records=seeded_records,
    )


def ensure_work_item(session: Session, item: DemoWorkItem) -> int:
    work_item = session.get(WorkItem, str(item["id"]))
    created = work_item is None
    if work_item is None:
        work_item = WorkItem(id=str(item["id"]), title=str(item["title"]))
        session.add(work_item)
    work_item.title = str(item["title"])
    work_item.status = str(item["status"])
    work_item.priority = int(item["priority"])
    work_item.risk = str(item["risk"])
    work_item.work_type = str(item["work_type"])
    work_item.autonomy_mode = str(item["autonomy_mode"])
    work_item.expected_touch = str(item["expected_touch"])
    work_item.acceptance = str(item["acceptance"])
    work_item.validation = str(item["validation"])
    return 1 if created else 0


def ensure_conflict_keys(
    session: Session,
    *,
    work_item_id: str,
    conflict_keys: tuple[str, ...],
) -> int:
    existing = set(
        session.scalars(
            select(WorkItemConflictKey.conflict_key).where(
                WorkItemConflictKey.work_item_id == work_item_id
            )
        )
    )
    created = 0
    for key in conflict_keys:
        if key not in existing:
            session.add(
                WorkItemConflictKey(work_item_id=work_item_id, conflict_key=key)
            )
            created += 1
    return created


def ensure_dependencies(
    session: Session,
    *,
    work_item_id: str,
    dependency_ids: tuple[str, ...],
) -> int:
    existing = set(
        session.scalars(
            select(WorkItemDependency.depends_on_work_item_id).where(
                WorkItemDependency.work_item_id == work_item_id
            )
        )
    )
    created = 0
    for dependency_id in dependency_ids:
        if dependency_id not in existing:
            session.add(
                WorkItemDependency(
                    work_item_id=work_item_id,
                    depends_on_work_item_id=dependency_id,
                )
            )
            created += 1
    return created


def ensure_demo_worker_state(session: Session, *, now: datetime) -> int:
    created = 0
    running_lease = ensure_lease(
        session,
        lease_id="m1-demo-running-lease",
        work_item_id="m1-demo-running",
        status=LeaseStatus.ACTIVE,
        fencing_token="m1-demo-running-token",
        heartbeat_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    stale_lease = ensure_lease(
        session,
        lease_id="m1-demo-stale-lease",
        work_item_id="m1-demo-stale-lease",
        status=LeaseStatus.ACTIVE,
        fencing_token="m1-demo-stale-token",
        heartbeat_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    created += running_lease + stale_lease
    created += ensure_lock_holder(
        session,
        lock_id="m1-demo-running-lock",
        conflict_key="runtime:worker",
        lease_id="m1-demo-running-lease",
    )
    created += ensure_lock_holder(
        session,
        lock_id="m1-demo-stale-lock",
        conflict_key="runtime:lease-recovery",
        lease_id="m1-demo-stale-lease",
    )
    created += ensure_worker_run(
        session,
        run_id="m1-demo-running-run",
        work_item_id="m1-demo-running",
        lease_id="m1-demo-running-lease",
        heartbeat_at=now,
    )
    return created


def ensure_lease(
    session: Session,
    *,
    lease_id: str,
    work_item_id: str,
    status: LeaseStatus,
    fencing_token: str,
    heartbeat_at: datetime,
    expires_at: datetime,
) -> int:
    lease = session.get(Lease, lease_id)
    created = lease is None
    if lease is None:
        lease = Lease(
            id=lease_id,
            work_item_id=work_item_id,
            owner="m1-demo-slot",
            status=str(status),
            fencing_token=fencing_token,
            expires_at=expires_at,
        )
        session.add(lease)
    lease.work_item_id = work_item_id
    lease.status = str(status)
    lease.fencing_token = fencing_token
    lease.heartbeat_at = heartbeat_at
    lease.expires_at = expires_at
    return 1 if created else 0


def ensure_lock_holder(
    session: Session,
    *,
    lock_id: str,
    conflict_key: str,
    lease_id: str,
) -> int:
    lock = session.get(LockHolder, lock_id)
    created = lock is None
    if lock is None:
        lock = LockHolder(
            id=lock_id,
            conflict_key=conflict_key,
            source="lease",
            lease_id=lease_id,
        )
        session.add(lock)
    lock.conflict_key = conflict_key
    lock.source = "lease"
    lock.lease_id = lease_id
    lock.released_at = None
    return 1 if created else 0


def ensure_worker_run(
    session: Session,
    *,
    run_id: str,
    work_item_id: str,
    lease_id: str,
    heartbeat_at: datetime,
) -> int:
    run = session.get(WorkerRun, run_id)
    created = run is None
    if run is None:
        run = WorkerRun(
            id=run_id,
            work_item_id=work_item_id,
            lease_id=lease_id,
            role=str(WorkerRole.WORKER),
            status=str(WorkerRunStatus.RUNNING),
            validation={},
            public_mutations={},
            cost_summary={},
        )
        session.add(run)
    run.work_item_id = work_item_id
    run.lease_id = lease_id
    run.role = str(WorkerRole.WORKER)
    run.status = str(WorkerRunStatus.RUNNING)
    run.result = None
    run.started_at = heartbeat_at - timedelta(minutes=5)
    run.heartbeat_at = heartbeat_at
    run.closed_at = None
    run.validation = {"smoke": "pending"}
    run.public_mutations = {}
    run.cost_summary = {}
    return 1 if created else 0


def ensure_demo_repository_state(session: Session, *, now: datetime) -> int:
    created = ensure_repository(session)
    created += ensure_pull_request(
        session,
        pr_id="m1-demo-waiting-pr",
        work_item_id="m1-demo-waiting",
        provider_pr_id="m1-demo-pr-1",
        number=101,
        head_sha="m1-demo-head-waiting",
        stale=False,
    )
    created += ensure_check_summary(
        session,
        check_id="m1-demo-waiting-check",
        pull_request_id="m1-demo-waiting-pr",
        name="pytest",
        head_sha="m1-demo-head-waiting",
        status=CheckStatus.IN_PROGRESS,
        conclusion=CheckConclusion.UNKNOWN,
        stale=False,
    )
    created += ensure_review_summary(
        session,
        review_id="m1-demo-waiting-review",
        pull_request_id="m1-demo-waiting-pr",
        state=ReviewGateState.WAITING,
        unresolved_count=0,
        stale=False,
    )
    created += ensure_pull_request(
        session,
        pr_id="m1-demo-review-pr",
        work_item_id="m1-demo-review",
        provider_pr_id="m1-demo-pr-2",
        number=102,
        head_sha="m1-demo-head-review",
        stale=True,
    )
    created += ensure_review_summary(
        session,
        review_id="m1-demo-strict-review",
        pull_request_id="m1-demo-review-pr",
        state=ReviewGateState.UNRESOLVED_THREADS,
        unresolved_count=2,
        stale=True,
    )
    created += ensure_pull_request(
        session,
        pr_id="m1-demo-failed-pr",
        work_item_id="m1-demo-failed",
        provider_pr_id="m1-demo-pr-3",
        number=103,
        head_sha="m1-demo-head-failed",
        stale=False,
    )
    created += ensure_check_summary(
        session,
        check_id="m1-demo-failed-check",
        pull_request_id="m1-demo-failed-pr",
        name="pytest",
        head_sha="m1-demo-head-failed",
        status=CheckStatus.COMPLETED,
        conclusion=CheckConclusion.FAILURE,
        stale=False,
    )
    created += ensure_review_summary(
        session,
        review_id="m1-demo-failed-review",
        pull_request_id="m1-demo-failed-pr",
        state=ReviewGateState.APPROVED,
        unresolved_count=0,
        stale=False,
    )
    created += ensure_inbound_failure(session)
    created += ensure_sync_failure(session, now=now)
    return created


def ensure_repository(session: Session) -> int:
    repository = session.get(Repository, DEMO_REPOSITORY_ID)
    created = repository is None
    if repository is None:
        repository = Repository(
            id=DEMO_REPOSITORY_ID,
            provider=str(RepositoryProvider.GITHUB),
            provider_repo_id="m1-demo-repo",
            name="example/m1-demo",
            default_branch="main",
            sync_status="failed",
        )
        session.add(repository)
    repository.provider = str(RepositoryProvider.GITHUB)
    repository.provider_repo_id = "m1-demo-repo"
    repository.name = "example/m1-demo"
    repository.default_branch = "main"
    repository.sync_status = "failed"
    return 1 if created else 0


def ensure_pull_request(
    session: Session,
    *,
    pr_id: str,
    work_item_id: str,
    provider_pr_id: str,
    number: int,
    head_sha: str,
    stale: bool,
) -> int:
    pull_request = session.get(RepoPullRequest, pr_id)
    created = pull_request is None
    if pull_request is None:
        pull_request = RepoPullRequest(
            id=pr_id,
            repository_id=DEMO_REPOSITORY_ID,
            provider_pr_id=provider_pr_id,
            number=number,
            url=f"https://example.test/pull/{number}",
            state="open",
            draft=False,
            merged=False,
        )
        session.add(pull_request)
    pull_request.repository_id = DEMO_REPOSITORY_ID
    pull_request.work_item_id = work_item_id
    pull_request.provider_pr_id = provider_pr_id
    pull_request.number = number
    pull_request.url = f"https://example.test/pull/{number}"
    pull_request.state = "open"
    pull_request.draft = False
    pull_request.head_branch = f"m1-demo-{number}"
    pull_request.head_sha = head_sha
    pull_request.merged = False
    pull_request.stale = stale
    return 1 if created else 0


def ensure_check_summary(
    session: Session,
    *,
    check_id: str,
    pull_request_id: str,
    name: str,
    head_sha: str,
    status: CheckStatus,
    conclusion: CheckConclusion,
    stale: bool,
) -> int:
    check = session.get(RepoCheckSummary, check_id)
    created = check is None
    if check is None:
        check = RepoCheckSummary(
            id=check_id,
            pull_request_id=pull_request_id,
            name=name,
            status=str(status),
            conclusion=str(conclusion),
            required=True,
            stale=stale,
        )
        session.add(check)
    check.pull_request_id = pull_request_id
    check.name = name
    check.status = str(status)
    check.conclusion = str(conclusion)
    check.head_sha = head_sha
    check.required = True
    check.stale = stale
    return 1 if created else 0


def ensure_review_summary(
    session: Session,
    *,
    review_id: str,
    pull_request_id: str,
    state: ReviewGateState,
    unresolved_count: int,
    stale: bool,
) -> int:
    review = session.get(RepoReviewSummary, review_id)
    created = review is None
    if review is None:
        review = RepoReviewSummary(
            id=review_id,
            pull_request_id=pull_request_id,
            state=str(state),
            unresolved_count=unresolved_count,
            stale=stale,
            summary={},
        )
        session.add(review)
    review.pull_request_id = pull_request_id
    review.state = str(state)
    review.unresolved_count = unresolved_count
    review.stale = stale
    review.summary = {"source": "m1-demo"}
    return 1 if created else 0


def ensure_inbound_failure(session: Session) -> int:
    event = session.get(InboundEvent, "m1-demo-inbound-failure")
    created = event is None
    if event is None:
        event = InboundEvent(
            id="m1-demo-inbound-failure",
            provider=str(RepositoryProvider.GITHUB),
            idempotency_key="m1-demo-delivery",
            event_type="check_run",
            payload_hash="m1-demo-hash",
            status=str(EventStatus.FAILED),
        )
        session.add(event)
    event.provider = str(RepositoryProvider.GITHUB)
    event.repository_id = DEMO_REPOSITORY_ID
    event.idempotency_key = "m1-demo-delivery"
    event.event_type = "check_run"
    event.action = "completed"
    event.external_id = "m1-demo-check-run"
    event.payload_hash = "m1-demo-hash"
    event.status = str(EventStatus.FAILED)
    event.error = "demo failure"
    return 1 if created else 0


def ensure_sync_failure(session: Session, *, now: datetime) -> int:
    cursor = session.get(SyncCursor, "m1-demo-sync-cursor")
    created = cursor is None
    if cursor is None:
        cursor = SyncCursor(
            id="m1-demo-sync-cursor",
            provider=str(RepositoryProvider.GITHUB),
            repository_id=DEMO_REPOSITORY_ID,
            sync_kind="poll",
        )
        session.add(cursor)
    cursor.provider = str(RepositoryProvider.GITHUB)
    cursor.repository_id = DEMO_REPOSITORY_ID
    cursor.sync_kind = "poll"
    cursor.cursor = "m1-demo-cursor"
    cursor.last_failure_at = now
    cursor.last_error = "demo sync failure"
    return 1 if created else 0


def ensure_audit_event(
    session: Session,
    *,
    event_id: str,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str,
    summary: str,
    details: dict[str, object],
) -> int:
    event = session.get(AuditEvent, event_id)
    created = event is None
    if event is None:
        event = AuditEvent(
            id=event_id,
            actor=actor,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            summary=summary,
            details=details,
        )
        session.add(event)
    event.actor = actor
    event.action = action
    event.subject_type = subject_type
    event.subject_id = subject_id
    event.summary = summary
    event.details = details
    return 1 if created else 0
