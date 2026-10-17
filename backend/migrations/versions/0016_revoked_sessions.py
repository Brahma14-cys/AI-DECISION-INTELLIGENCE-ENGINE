"""Persist revoked advocate sessions so logout invalidates copied cookies."""

from alembic import op
import sqlalchemy as sa


revision = "0016_revoked_sessions"
down_revision = "0015_case_deadlines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti_hash"),
    )
    op.create_index("ix_revoked_sessions_expires_at", "revoked_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_expires_at", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
