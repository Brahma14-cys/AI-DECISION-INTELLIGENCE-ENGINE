"""Add advocate-managed dates and deadline items to cases."""

from alembic import op
import sqlalchemy as sa


revision = "0015_case_deadlines"
down_revision = "0014_workflow_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_deadlines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_deadlines_case_id", "case_deadlines", ["case_id"])
    op.create_index("ix_case_deadlines_due_date", "case_deadlines", ["due_date"])


def downgrade() -> None:
    op.drop_index("ix_case_deadlines_due_date", table_name="case_deadlines")
    op.drop_index("ix_case_deadlines_case_id", table_name="case_deadlines")
    op.drop_table("case_deadlines")
