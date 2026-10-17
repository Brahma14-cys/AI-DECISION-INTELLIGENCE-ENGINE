"""Persist sentence, entity, and legal-reference extraction items."""

from alembic import op
import sqlalchemy as sa


revision = "0006_structured_extraction_items"
down_revision = "0005_case_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_analysis_extraction_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_text_unit_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("document_text_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_kind", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("legal_role", sa.String(length=120), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extractor", sa.String(length=24), nullable=False),
    )
    op.create_index(
        "ix_case_analysis_extraction_items_analysis_run_id",
        "case_analysis_extraction_items",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_case_analysis_extraction_items_source_text_unit_id",
        "case_analysis_extraction_items",
        ["source_text_unit_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_case_analysis_extraction_items_source_text_unit_id",
        table_name="case_analysis_extraction_items",
    )
    op.drop_index(
        "ix_case_analysis_extraction_items_analysis_run_id",
        table_name="case_analysis_extraction_items",
    )
    op.drop_table("case_analysis_extraction_items")
