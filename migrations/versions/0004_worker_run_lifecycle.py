"""worker run lifecycle timestamps."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_worker_run_lifecycle"
down_revision: str | None = "0003_command_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "worker_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "worker_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "worker_runs",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_worker_runs_open_lease",
        "worker_runs",
        ["lease_id"],
        unique=True,
        sqlite_where=sa.text("lease_id IS NOT NULL AND status <> 'closed'"),
        postgresql_where=sa.text("lease_id IS NOT NULL AND status <> 'closed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_worker_runs_open_lease", table_name="worker_runs")
    op.drop_column("worker_runs", "closed_at")
    op.drop_column("worker_runs", "heartbeat_at")
    op.drop_column("worker_runs", "started_at")
