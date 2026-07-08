from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from kairota.contracts.enums import (
    AutonomyMode,
    CheckConclusion,
    CheckStatus,
    EventStatus,
    LeaseStatus,
    LockHolderSource,
    OutboxStatus,
    PullRequestState,
    RepositoryProvider,
    ReviewGateState,
    RiskLevel,
    SchedulerDecisionCode,
    WorkerRole,
    WorkerRunResult,
    WorkerRunStatus,
    WorkItemStatus,
    WorkType,
)
from kairota.models.base import Base


def new_id() -> str:
    return str(uuid4())


def enum_values(enum_type: type[Enum]) -> str:
    values = ", ".join(f"'{member.value}'" for member in enum_type.__members__.values())
    return f"({values})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkItem(TimestampMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint(
            f"status in {enum_values(WorkItemStatus)}", "ck_work_items_status"
        ),
        CheckConstraint(f"risk in {enum_values(RiskLevel)}", "ck_work_items_risk"),
        CheckConstraint(f"work_type in {enum_values(WorkType)}", "ck_work_items_type"),
        CheckConstraint(
            f"autonomy_mode in {enum_values(AutonomyMode)}",
            "ck_work_items_autonomy",
        ),
        CheckConstraint("priority >= 0", "ck_work_items_priority_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkItemStatus.NEEDS_TRIAGE.value,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    risk: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RiskLevel.MEDIUM.value,
    )
    work_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkType.IMPLEMENTATION.value,
    )
    autonomy_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AutonomyMode.AI_ASSISTED.value,
    )
    acceptance: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[str | None] = mapped_column(Text)
    expected_touch: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))


class WorkItemDependency(Base):
    __tablename__ = "work_item_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "work_item_id",
            "depends_on_work_item_id",
            name="uq_work_item_dependencies_edge",
        ),
        CheckConstraint(
            "work_item_id <> depends_on_work_item_id",
            "ck_work_item_dependencies_no_self",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    depends_on_work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
    )


class WorkItemConflictKey(Base):
    __tablename__ = "work_item_conflict_keys"
    __table_args__ = (
        UniqueConstraint(
            "work_item_id",
            "conflict_key",
            name="uq_work_item_conflict_keys_item_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    conflict_key: Mapped[str] = mapped_column(String(300), nullable=False)


class Repository(TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_repo_id", name="uq_repositories_provider_id"
        ),
        CheckConstraint(
            f"provider in {enum_values(RepositoryProvider)}", "ck_repositories_provider"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_repo_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(120), nullable=False, default="main"
    )
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )


class ExternalRef(TimestampMixin, Base):
    __tablename__ = "external_refs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_type",
            "external_id",
            name="uq_external_refs_provider_type_id",
        ),
        CheckConstraint(
            f"provider in {enum_values(RepositoryProvider)}",
            "ck_external_refs_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500))
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id"))
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"))


class SchedulerGuard(Base):
    __tablename__ = "scheduler_guards"
    __table_args__ = (UniqueConstraint("queue_key", name="uq_scheduler_guards_queue"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    queue_key: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SchedulerCycle(TimestampMixin, Base):
    __tablename__ = "scheduler_cycles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    queue_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_version: Mapped[str | None] = mapped_column(String(160))
    result: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    assigned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SchedulerDecision(TimestampMixin, Base):
    __tablename__ = "scheduler_decisions"
    __table_args__ = (
        CheckConstraint(
            f"code in {enum_values(SchedulerDecisionCode)}",
            "ck_scheduler_decisions_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cycle_id: Mapped[str] = mapped_column(
        ForeignKey("scheduler_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    blocking_facts: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class Lease(TimestampMixin, Base):
    __tablename__ = "leases"
    __table_args__ = (
        CheckConstraint(f"status in {enum_values(LeaseStatus)}", "ck_leases_status"),
        UniqueConstraint("fencing_token", name="uq_leases_fencing_token"),
        Index(
            "uq_leases_active_work_item",
            "work_item_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id"), nullable=False
    )
    owner: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=LeaseStatus.ACTIVE.value,
    )
    fencing_token: Mapped[str] = mapped_column(String(120), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class LockHolder(TimestampMixin, Base):
    __tablename__ = "lock_holders"
    __table_args__ = (
        CheckConstraint(
            f"source in {enum_values(LockHolderSource)}", "ck_lock_holders_source"
        ),
        Index(
            "uq_lock_holders_active_key",
            "conflict_key",
            unique=True,
            sqlite_where=text("released_at IS NULL"),
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conflict_key: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    lease_id: Mapped[str | None] = mapped_column(ForeignKey("leases.id"))
    pull_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("repo_pull_requests.id")
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerRun(TimestampMixin, Base):
    __tablename__ = "worker_runs"
    __table_args__ = (
        CheckConstraint(f"role in {enum_values(WorkerRole)}", "ck_worker_runs_role"),
        CheckConstraint(
            f"status in {enum_values(WorkerRunStatus)}", "ck_worker_runs_status"
        ),
        CheckConstraint(
            f"result is null or result in {enum_values(WorkerRunResult)}",
            "ck_worker_runs_result",
        ),
        Index(
            "uq_worker_runs_open_lease",
            "lease_id",
            unique=True,
            sqlite_where=text("lease_id IS NOT NULL AND status <> 'closed'"),
            postgresql_where=text("lease_id IS NOT NULL AND status <> 'closed'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("work_items.id"), nullable=False
    )
    lease_id: Mapped[str | None] = mapped_column(ForeignKey("leases.id"))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkerRunStatus.PLANNED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(String(32))
    validation: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    public_mutations: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    cost_summary: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class RepoPullRequest(TimestampMixin, Base):
    __tablename__ = "repo_pull_requests"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "provider_pr_id",
            name="uq_repo_pull_requests_provider_pr",
        ),
        CheckConstraint(
            f"state in {enum_values(PullRequestState)}", "ck_repo_pr_state"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), nullable=False
    )
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id"))
    provider_pr_id: Mapped[str] = mapped_column(String(160), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    head_branch: Mapped[str | None] = mapped_column(String(240))
    head_sha: Mapped[str | None] = mapped_column(String(80))
    merged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(80))
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RepoCheckSummary(TimestampMixin, Base):
    __tablename__ = "repo_check_summaries"
    __table_args__ = (
        UniqueConstraint(
            "pull_request_id",
            "name",
            "head_sha",
            name="uq_repo_check_summaries_pr_name_head",
        ),
        CheckConstraint(
            f"status in {enum_values(CheckStatus)}", "ck_repo_checks_status"
        ),
        CheckConstraint(
            f"conclusion in {enum_values(CheckConclusion)}",
            "ck_repo_checks_conclusion",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pull_request_id: Mapped[str] = mapped_column(
        ForeignKey("repo_pull_requests.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    conclusion: Mapped[str] = mapped_column(String(32), nullable=False)
    head_sha: Mapped[str | None] = mapped_column(String(80))
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details_url: Mapped[str | None] = mapped_column(String(500))


class RepoReviewSummary(TimestampMixin, Base):
    __tablename__ = "repo_review_summaries"
    __table_args__ = (
        UniqueConstraint("pull_request_id", name="uq_repo_review_summaries_pr"),
        CheckConstraint(
            f"state in {enum_values(ReviewGateState)}",
            "ck_repo_review_summaries_state",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pull_request_id: Mapped[str] = mapped_column(
        ForeignKey("repo_pull_requests.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    summary: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )


class SyncCursor(TimestampMixin, Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "repository_id",
            "sync_kind",
            name="uq_sync_cursors_scope",
        ),
        CheckConstraint(
            f"provider in {enum_values(RepositoryProvider)}", "ck_sync_cursors_provider"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id"), nullable=False
    )
    sync_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(500))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class InboundEvent(TimestampMixin, Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "idempotency_key", name="uq_inbound_events_idempotency"
        ),
        CheckConstraint(
            f"provider in {enum_values(RepositoryProvider)}",
            "ck_inbound_events_provider",
        ),
        CheckConstraint(
            f"status in {enum_values(EventStatus)}", "ck_inbound_events_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("repositories.id"))
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str | None] = mapped_column(String(120))
    external_id: Mapped[str | None] = mapped_column(String(240))
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EventStatus.PENDING.value
    )
    error: Mapped[str | None] = mapped_column(Text)


class OutboxEvent(TimestampMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbox_events_idempotency"),
        CheckConstraint(
            f"status in {enum_values(OutboxStatus)}", "ck_outbox_events_status"
        ),
        CheckConstraint("retry_count >= 0", "ck_outbox_events_retry_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    target: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=OutboxStatus.PENDING.value
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class CommandRequest(TimestampMixin, Base):
    __tablename__ = "command_requests"
    __table_args__ = (
        UniqueConstraint(
            "command_name",
            "idempotency_key",
            name="uq_command_requests_command_key",
        ),
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            "ck_command_requests_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    command_name: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    result_id: Mapped[str | None] = mapped_column(String(160))
    response_body: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    error: Mapped[str | None] = mapped_column(Text)


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
