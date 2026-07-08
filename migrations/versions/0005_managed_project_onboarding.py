"""managed project onboarding."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_managed_project_onboarding"
down_revision: str | None = "0004_worker_run_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_items") as batch_op:
        batch_op.add_column(
            sa.Column("repository_id", sa.String(length=36), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_work_items_repository_id_repositories",
            "repositories",
            ["repository_id"],
            ["id"],
        )
    with op.batch_alter_table("scheduler_cycles") as batch_op:
        batch_op.add_column(
            sa.Column("repository_id", sa.String(length=36), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_scheduler_cycles_repository_id_repositories",
            "repositories",
            ["repository_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scheduler_cycles") as batch_op:
        batch_op.drop_constraint(
            "fk_scheduler_cycles_repository_id_repositories",
            type_="foreignkey",
        )
        batch_op.drop_column("repository_id")
    with op.batch_alter_table("work_items") as batch_op:
        batch_op.drop_constraint(
            "fk_work_items_repository_id_repositories",
            type_="foreignkey",
        )
        batch_op.drop_column("repository_id")
