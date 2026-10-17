"""Persist the one-advocate first-run account."""

from alembic import op
import sqlalchemy as sa


revision = "0017_advocate_account"
down_revision = "0016_revoked_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advocate_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        # EncryptedText stores ciphertext in a text column; encryption and
        # decryption are applied by the SQLAlchemy model type.
        sa.Column("session_secret", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_advocate_accounts_singleton"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade() -> None:
    op.drop_table("advocate_accounts")
