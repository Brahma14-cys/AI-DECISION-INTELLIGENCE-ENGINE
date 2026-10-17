"""Store source-linked case claim support reviews."""

from alembic import op
import sqlalchemy as sa


revision = "0004_claim_reviews"
down_revision = "0003_case_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_analysis_runs",
        sa.Column("claim_review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "case_claim_reviews",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_kind", sa.String(length=24), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column(
            "source_fact_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_analysis_facts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("support_status", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("is_overstated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("overstatement_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_case_claim_reviews_analysis_run_id", "case_claim_reviews", ["analysis_run_id"])
    op.create_table(
        "case_claim_review_evidence",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_review_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_claim_reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_fact_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_analysis_facts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("claim_review_id", "evidence_fact_id", name="uq_claim_review_evidence_pair"),
    )
    op.create_index(
        "ix_case_claim_review_evidence_claim_review_id",
        "case_claim_review_evidence",
        ["claim_review_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_claim_review_evidence_claim_review_id", table_name="case_claim_review_evidence")
    op.drop_table("case_claim_review_evidence")
    op.drop_index("ix_case_claim_reviews_analysis_run_id", table_name="case_claim_reviews")
    op.drop_table("case_claim_reviews")
    op.drop_column("case_analysis_runs", "claim_review_count")
