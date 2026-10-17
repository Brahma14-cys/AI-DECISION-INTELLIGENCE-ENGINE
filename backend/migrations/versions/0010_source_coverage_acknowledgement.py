"""Record advocate acknowledgement when analysis uses incomplete sources."""

from alembic import op
import sqlalchemy as sa


revision = "0010_coverage_ack"
down_revision = "0009_durable_case_job_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_analysis_runs",
        sa.Column("incomplete_sources_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "case_summary_runs",
        sa.Column("incomplete_sources_acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("case_summary_runs", "incomplete_sources_acknowledged")
    op.drop_column("case_analysis_runs", "incomplete_sources_acknowledged")
