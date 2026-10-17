"""Persist advocate claims with queued analysis runs for worker recovery."""

from alembic import op
import sqlalchemy as sa


revision = "0009_durable_case_job_claims"
down_revision = "0008_encrypt_sensitive_case_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_analysis_runs",
        sa.Column("advocate_claims", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("case_analysis_runs", "advocate_claims")
