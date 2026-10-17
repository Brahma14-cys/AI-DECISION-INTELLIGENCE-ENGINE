"""Store integrated source-cited case summaries."""

from alembic import op
import sqlalchemy as sa


revision = "0005_case_summaries"
down_revision = "0004_claim_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_summary_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("text_unit_count", sa.Integer(), nullable=False),
        sa.Column("point_count", sa.Integer(), nullable=False),
        sa.Column("narrative_summary", sa.JSON(), nullable=False),
        sa.Column("structured_summary", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_case_summary_runs_case_id", "case_summary_runs", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_summary_runs_case_id", table_name="case_summary_runs")
    op.drop_table("case_summary_runs")
