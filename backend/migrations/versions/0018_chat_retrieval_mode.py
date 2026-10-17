"""Record how each assistant answer retrieved case passages."""

from alembic import op
import sqlalchemy as sa


revision = "0018_chat_retrieval_mode"
down_revision = "0017_advocate_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_chat_messages", sa.Column("retrieval_mode", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("case_chat_messages", "retrieval_mode")
