"""Queue the case-analysis stages when a complete set of sources is ready."""

from uuid import UUID
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import lock_case_for_update
from app.db.models import (
    Case,
    CaseAnalysisRun,
    CaseDocument,
    CaseKnowledgeGraphRun,
    DocumentTextUnit,
)


def enqueue_case_analysis_if_ready(db: Session, case_id: UUID) -> bool:
    """Queue one analysis after every source has completed extraction cleanly.

    Documents requiring review are deliberately left for advocate review and
    explicit acknowledgement through the normal analysis endpoint.
    """
    if settings.app_env.strip().lower() == "test":
        return False

    from app.services.case_analysis_processing import gemini_is_ready

    if not gemini_is_ready():
        return False

    # Serialize automatic and advocate-triggered queueing for this case.
    case = lock_case_for_update(db, case_id)
    if case is None:
        return False

    documents = list(db.scalars(
        select(CaseDocument).where(CaseDocument.case_id == case_id)
        .order_by(CaseDocument.uploaded_at)
    ).all())
    if not documents or any(document.processing_status != "processed" for document in documents):
        return False

    latest_upload = max(document.uploaded_at for document in documents)
    latest_run = db.scalar(
        select(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id)
        .order_by(CaseAnalysisRun.created_at.desc()).limit(1)
    )
    if latest_run is not None:
        if latest_run.status in {"queued", "processing"}:
            return False
        if latest_run.created_at >= latest_upload:
            return False

    text_unit_count = db.scalar(
        select(func.count(DocumentTextUnit.id))
        .join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
        .where(CaseDocument.case_id == case_id, DocumentTextUnit.text != "")
    ) or 0
    if text_unit_count == 0:
        return False

    db.add(CaseAnalysisRun(
        case_id=case_id,
        status="queued",
        provider="google_gemini",
        model=settings.gemini_model,
        document_count=len(documents),
        text_unit_count=text_unit_count,
        advocate_claims=[],
        incomplete_sources_acknowledged=False,
    ))
    case.updated_at = datetime.now(UTC)
    db.commit()
    return True


def enqueue_case_graph_after_analysis(db: Session, analysis_run: CaseAnalysisRun) -> bool:
    """Queue a graph build only when the completed analysis covers current files."""
    if settings.app_env.strip().lower() == "test":
        return False

    from app.services.knowledge_graph_processing import graph_is_configured

    if not graph_is_configured():
        return False

    case = lock_case_for_update(db, analysis_run.case_id)
    if case is None:
        return False

    latest_upload = db.scalar(
        select(func.max(CaseDocument.uploaded_at))
        .where(CaseDocument.case_id == analysis_run.case_id)
    )
    if latest_upload is not None and analysis_run.created_at < latest_upload:
        return False

    existing = db.scalar(
        select(CaseKnowledgeGraphRun).where(
            CaseKnowledgeGraphRun.case_id == analysis_run.case_id,
            CaseKnowledgeGraphRun.analysis_run_id == analysis_run.id,
        ).limit(1)
    )
    if existing is not None:
        return False

    db.add(CaseKnowledgeGraphRun(
        case_id=analysis_run.case_id,
        analysis_run_id=analysis_run.id,
        status="queued",
        provider="neo4j",
        embedding_model=settings.graph_embedding_model,
    ))
    db.commit()
    return True
