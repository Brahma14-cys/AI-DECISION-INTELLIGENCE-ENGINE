"""Add encrypted case chat conversations and messages."""

from alembic import op
import sqlalchemy as sa


revision = "0013_case_chat"
down_revision = "0012_case_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_chat_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_chat_conversations_case_id", "case_chat_conversations", ["case_id"])
    op.create_table(
        "case_chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["case_chat_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_chat_messages_conversation_id", "case_chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_case_chat_messages_conversation_id", table_name="case_chat_messages")
    op.drop_table("case_chat_messages")
    op.drop_index("ix_case_chat_conversations_case_id", table_name="case_chat_conversations")
    op.drop_table("case_chat_conversations")
