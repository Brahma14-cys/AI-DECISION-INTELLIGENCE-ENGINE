"""Track case knowledge graph build runs and encrypted snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0012_case_knowledge_graph"
down_revision = "0011_analysis_retrieval_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_knowledge_graph_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("graph_snapshot", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["case_analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_case_knowledge_graph_runs_case_id",
        "case_knowledge_graph_runs",
        ["case_id"],
    )
    op.create_index(
        "ix_case_knowledge_graph_runs_analysis_run_id",
        "case_knowledge_graph_runs",
        ["analysis_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_knowledge_graph_runs_analysis_run_id", table_name="case_knowledge_graph_runs")
    op.drop_index("ix_case_knowledge_graph_runs_case_id", table_name="case_knowledge_graph_runs")
    op.drop_table("case_knowledge_graph_runs")
