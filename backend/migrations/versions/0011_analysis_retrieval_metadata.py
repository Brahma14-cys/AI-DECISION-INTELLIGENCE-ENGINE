"""Persist retrieval coverage metadata for each case analysis run."""

from alembic import op
import sqlalchemy as sa


revision = "0011_analysis_retrieval_metadata"
down_revision = "0010_coverage_ack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_analysis_runs", sa.Column("retrieval_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("case_analysis_runs", "retrieval_metadata")
