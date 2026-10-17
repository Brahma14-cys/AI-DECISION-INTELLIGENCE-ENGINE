"""Persist case facts and source-linked cross-document findings."""

from alembic import op
import sqlalchemy as sa


revision = "0003_case_analysis"
down_revision = "0002_document_text_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_analysis_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("text_unit_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_case_analysis_runs_case_id", "case_analysis_runs", ["case_id"])

    op.create_table(
        "case_analysis_facts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", sa.Uuid(as_uuid=True), sa.ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_text_unit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("document_text_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fact_type", sa.String(length=32), nullable=False),
        sa.Column("topic_key", sa.String(length=160), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=500), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_case_analysis_facts_analysis_run_id", "case_analysis_facts", ["analysis_run_id"])
    op.create_index("ix_case_analysis_facts_source_text_unit_id", "case_analysis_facts", ["source_text_unit_id"])
    op.create_index("ix_case_analysis_facts_topic_key", "case_analysis_facts", ["topic_key"])

    op.create_table(
        "case_analysis_findings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("analysis_run_id", sa.Uuid(as_uuid=True), sa.ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_type", sa.String(length=24), nullable=False),
        sa.Column("relation_label", sa.String(length=32), nullable=True),
        sa.Column("left_fact_id", sa.Uuid(as_uuid=True), sa.ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_fact_id", sa.Uuid(as_uuid=True), sa.ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_case_analysis_findings_analysis_run_id", "case_analysis_findings", ["analysis_run_id"])


def downgrade() -> None:
    op.drop_index("ix_case_analysis_findings_analysis_run_id", table_name="case_analysis_findings")
    op.drop_table("case_analysis_findings")
    op.drop_index("ix_case_analysis_facts_topic_key", table_name="case_analysis_facts")
    op.drop_index("ix_case_analysis_facts_source_text_unit_id", table_name="case_analysis_facts")
    op.drop_index("ix_case_analysis_facts_analysis_run_id", table_name="case_analysis_facts")
    op.drop_table("case_analysis_facts")
    op.drop_index("ix_case_analysis_runs_case_id", table_name="case_analysis_runs")
    op.drop_table("case_analysis_runs")
