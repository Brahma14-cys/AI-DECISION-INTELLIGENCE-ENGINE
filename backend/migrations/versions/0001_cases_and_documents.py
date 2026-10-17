"""Create cases and uploaded-document metadata."""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0001_cases_documents"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("client_reference", sa.String(length=120), nullable=True),
        sa.Column("court", sa.String(length=160), nullable=True),
        sa.Column("jurisdiction", sa.String(length=120), nullable=True),
        sa.Column("case_type", sa.String(length=120), nullable=True),
        sa.Column("stage", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "case_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column(
            "case_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("file_extension", sa.String(length=12), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "sha256", name="uq_case_documents_case_sha256"),
    )
    op.create_index("ix_case_documents_case_id", "case_documents", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_documents_case_id", table_name="case_documents")
    op.drop_table("case_documents")
    op.drop_table("cases")
