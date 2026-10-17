"""Widen sensitive string fields for authenticated ciphertext payloads."""

from alembic import op
import sqlalchemy as sa


revision = "0008_encrypt_sensitive_case_data"
down_revision = "0007_source_character_spans"
branch_labels = None
depends_on = None


_COLUMNS = [
    ("cases", "title", 200),
    ("cases", "client_reference", 120),
    ("cases", "court", 160),
    ("cases", "jurisdiction", 120),
    ("cases", "case_type", 120),
    ("cases", "stage", 120),
    ("case_documents", "original_filename", 255),
    ("case_analysis_facts", "topic_key", 160),
    ("case_analysis_facts", "normalized_value", 500),
    ("case_analysis_extraction_items", "category", 64),
    ("case_analysis_extraction_items", "legal_role", 120),
    ("case_analysis_findings", "relation_label", 32),
    ("case_claim_reviews", "support_status", 32),
]


def upgrade() -> None:
    op.drop_index("ix_case_analysis_facts_topic_key", table_name="case_analysis_facts")
    for table, column, length in _COLUMNS:
        op.alter_column(table, column, existing_type=sa.String(length=length), type_=sa.Text())


def downgrade() -> None:
    # Ciphertext is longer than the former VARCHAR constraints; narrowing these
    # columns can truncate data and must be handled by an explicit data migration.
    for table, column, length in reversed(_COLUMNS):
        op.alter_column(table, column, existing_type=sa.Text(), type_=sa.String(length=length))
    op.create_index("ix_case_analysis_facts_topic_key", "case_analysis_facts", ["topic_key"])
