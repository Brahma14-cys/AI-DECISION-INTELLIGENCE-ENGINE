"""Add source character spans to analysis facts and extraction items."""

from alembic import op
import sqlalchemy as sa


revision = "0007_source_character_spans"
down_revision = "0006_structured_extraction_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_analysis_facts", sa.Column("source_start_char", sa.Integer(), nullable=True))
    op.add_column("case_analysis_facts", sa.Column("source_end_char", sa.Integer(), nullable=True))
    op.add_column("case_analysis_extraction_items", sa.Column("source_start_char", sa.Integer(), nullable=True))
    op.add_column("case_analysis_extraction_items", sa.Column("source_end_char", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("case_analysis_extraction_items", "source_end_char")
    op.drop_column("case_analysis_extraction_items", "source_start_char")
    op.drop_column("case_analysis_facts", "source_end_char")
    op.drop_column("case_analysis_facts", "source_start_char")
