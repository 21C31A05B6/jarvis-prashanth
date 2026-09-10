"""Create workflows table for the Workflow Recording feature."""

from alembic import op
import sqlalchemy as sa


revision = "20260830_0005"
down_revision = "20260830_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflows_user_created", "workflows", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("workflows")
