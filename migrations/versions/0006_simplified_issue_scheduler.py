"""replace the M1 work queue with the managed Issue scheduler."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_simplified_issue_scheduler"
down_revision: str | None = "0005_managed_project_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in (
        "worker_runs",
        "lock_holders",
        "repo_check_summaries",
        "repo_review_summaries",
        "scheduler_decisions",
        "work_item_dependencies",
        "work_item_conflict_keys",
        "repo_pull_requests",
        "external_refs",
        "leases",
        "sync_cursors",
        "inbound_events",
        "scheduler_cycles",
        "work_items",
        "repositories",
        "outbox_events",
        "scheduler_guards",
        "audit_events",
        "command_requests",
    ):
        op.drop_table(table_name)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_repo_id", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_repo_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "managed_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("provider_issue_id", sa.String(length=160), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("source_state", sa.String(length=16), nullable=False),
        sa.Column("scheduling_state", sa.String(length=32), nullable=False),
        sa.Column("scheduling_version", sa.Integer(), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("analysis_completed", sa.Boolean(), nullable=False),
        sa.Column("manual_hold_reason", sa.String(length=500), nullable=True),
        sa.Column("in_progress_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.String(length=80), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "source_state in ('open', 'closed')",
            name="ck_managed_issues_source_state",
        ),
        sa.CheckConstraint(
            "scheduling_state in "
            "('needs_analysis', 'blocked', 'ready', 'in_progress', 'closed')",
            name="ck_managed_issues_scheduling_state",
        ),
        sa.CheckConstraint(
            "scheduling_version >= 0", name="ck_managed_issues_scheduling_version"
        ),
        sa.CheckConstraint(
            "analysis_version >= 0", name="ck_managed_issues_analysis_version"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "provider_issue_id", name="uq_managed_issues_provider_id"
        ),
        sa.UniqueConstraint("project_id", "number", name="uq_managed_issues_number"),
    )
    op.create_table(
        "issue_dependencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("depends_on_issue_id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "issue_id <> depends_on_issue_id", name="ck_issue_dependencies_no_self"
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["managed_issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_issue_id"], ["managed_issues.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issue_id", "depends_on_issue_id", name="uq_issue_dependencies_edge"
        ),
    )
    op.create_table(
        "project_sync_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("cursor", sa.String(length=500), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "health in ('unknown', 'syncing', 'healthy', 'error')",
            name="ck_project_sync_states_health",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "command_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("command_name", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_id", sa.String(length=160), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "status in ('running', 'completed', 'failed')",
            name="ck_command_requests_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "command_name", "idempotency_key", name="uq_command_requests_command_key"
        ),
    )
    op.create_table(
        "inbound_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("delivery_id", sa.String(length=240), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint(
            "status in ('pending', 'processed', 'failed')",
            name="ck_inbound_events_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_id", name="uq_inbound_events_delivery"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["issue_id"], ["managed_issues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "The simplified scheduler migration intentionally discards data."
    )


def timestamp_columns() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )
