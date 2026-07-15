from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from kairota.models.base import Base


def new_id() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_repo_id: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProjectSyncState(TimestampMixin, Base):
    __tablename__ = "project_sync_states"
    __table_args__ = (
        CheckConstraint(
            "health in ('unknown', 'syncing', 'healthy', 'error')",
            name="ck_project_sync_states_health",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    health: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    cursor: Mapped[str | None] = mapped_column(String(500))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ManagedIssue(TimestampMixin, Base):
    __tablename__ = "managed_issues"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "provider_issue_id", name="uq_managed_issues_provider_id"
        ),
        UniqueConstraint("project_id", "number", name="uq_managed_issues_number"),
        CheckConstraint(
            "source_state in ('open', 'closed')", name="ck_managed_issues_source_state"
        ),
        CheckConstraint(
            "scheduling_state in "
            "('needs_analysis', 'blocked', 'ready', 'in_progress', 'closed')",
            name="ck_managed_issues_scheduling_state",
        ),
        CheckConstraint(
            "scheduling_version >= 0", name="ck_managed_issues_scheduling_version"
        ),
        CheckConstraint(
            "analysis_version >= 0", name="ck_managed_issues_analysis_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    provider_issue_id: Mapped[str] = mapped_column(String(160), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open"
    )
    scheduling_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="needs_analysis"
    )
    scheduling_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analysis_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    manual_hold_reason: Mapped[str | None] = mapped_column(String(500))
    in_progress_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[str | None] = mapped_column(String(80))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IssueDependency(Base):
    __tablename__ = "issue_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "issue_id", "depends_on_issue_id", name="uq_issue_dependencies_edge"
        ),
        CheckConstraint(
            "issue_id <> depends_on_issue_id", name="ck_issue_dependencies_no_self"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issue_id: Mapped[str] = mapped_column(
        ForeignKey("managed_issues.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_issue_id: Mapped[str] = mapped_column(
        ForeignKey("managed_issues.id", ondelete="CASCADE"), nullable=False
    )


class CommandRequest(TimestampMixin, Base):
    __tablename__ = "command_requests"
    __table_args__ = (
        UniqueConstraint(
            "command_name", "idempotency_key", name="uq_command_requests_command_key"
        ),
        CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_command_requests_status",
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


class InboundEvent(TimestampMixin, Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint("delivery_id", name="uq_inbound_events_delivery"),
        CheckConstraint(
            "status in ('pending', 'processed', 'failed')",
            name="ck_inbound_events_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    delivery_id: Mapped[str] = mapped_column(String(240), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str | None] = mapped_column(String(120))
    issue_number: Mapped[int | None] = mapped_column(Integer)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    issue_id: Mapped[str | None] = mapped_column(ForeignKey("managed_issues.id"))
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
