"""Add steps column to task_records for the AI Task Planner / Task Automation feature."""

from alembic import op
import sqlalchemy as sa


revision = "20260830_0004"
down_revision = "20260829_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_records",
        sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("task_records", "steps")
