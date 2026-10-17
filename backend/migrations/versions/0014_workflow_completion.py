"""Add case workflow metadata, document labels, and advocate review state."""

from alembic import op
import sqlalchemy as sa


revision = "0014_workflow_completion"
down_revision = "0013_case_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("case_number", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("next_hearing_date", sa.Date(), nullable=True))
    op.add_column("case_documents", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("case_documents", sa.Column("document_type", sa.Text(), nullable=True))
    op.add_column("case_analysis_findings", sa.Column("review_status", sa.String(length=32), server_default="needs_review", nullable=False))
    op.add_column("case_analysis_findings", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_table(
        "case_analysis_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("correction_text", sa.Text(), nullable=True),
        sa.Column("correction_category", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["case_analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_run_id", "target_kind", "target_id", name="uq_case_analysis_review_target"),
    )
    op.create_index("ix_case_analysis_reviews_case_id", "case_analysis_reviews", ["case_id"])
    op.create_index("ix_case_analysis_reviews_analysis_run_id", "case_analysis_reviews", ["analysis_run_id"])
    op.create_table(
        "case_authority_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="needs_review", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "provider", "source_id", name="uq_case_authority_review_source"),
    )
    op.create_index("ix_case_authority_reviews_case_id", "case_authority_reviews", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_authority_reviews_case_id", table_name="case_authority_reviews")
    op.drop_table("case_authority_reviews")
    op.drop_index("ix_case_analysis_reviews_analysis_run_id", table_name="case_analysis_reviews")
    op.drop_index("ix_case_analysis_reviews_case_id", table_name="case_analysis_reviews")
    op.drop_table("case_analysis_reviews")
    op.drop_column("case_analysis_findings", "review_note")
    op.drop_column("case_analysis_findings", "review_status")
    op.drop_column("case_documents", "document_type")
    op.drop_column("case_documents", "description")
    op.drop_column("cases", "next_hearing_date")
    op.drop_column("cases", "case_number")
