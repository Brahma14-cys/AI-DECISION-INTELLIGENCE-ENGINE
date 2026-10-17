"""Store extracted document text with page or paragraph source locators."""

from alembic import op
import sqlalchemy as sa


revision = "0002_document_text_units"
down_revision = "0001_cases_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_documents", sa.Column("extraction_error", sa.Text(), nullable=True))
    op.create_table(
        "document_text_units",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("case_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unit_number", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("locator_label", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(length=32), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "unit_number", name="uq_document_text_units_document_unit"),
    )
    op.create_index("ix_document_text_units_document_id", "document_text_units", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_text_units_document_id", table_name="document_text_units")
    op.drop_table("document_text_units")
    op.drop_column("case_documents", "extraction_error")
