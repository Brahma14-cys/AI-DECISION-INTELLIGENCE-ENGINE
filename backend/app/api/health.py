from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal, is_database_ready
from app.core.durable_worker import get_worker_status
from app.core.auth import require_advocate
from app.db.models import CaseAnalysisRun, CaseDocument, CaseKnowledgeGraphRun, CaseSummaryRun


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict[str, str]:
    """Confirm the API process is running without depending on external services."""
    return {"status": "alive"}


@router.get("/ready")
def readiness() -> dict[str, str]:
    """Confirm the API can reach its configured database."""
    if not is_database_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ready", "database": "connected"}


@router.get("/worker", dependencies=[Depends(require_advocate)])
def worker_readiness() -> dict:
    """Expose queue liveness separately from database readiness."""
    enabled = settings.app_env.strip().lower() != "test"
    worker = get_worker_status()
    with SessionLocal() as db:
        documents = dict(db.execute(
            select(CaseDocument.processing_status, func.count(CaseDocument.id))
            .group_by(CaseDocument.processing_status)
        ).all())
        analysis = dict(db.execute(
            select(CaseAnalysisRun.status, func.count(CaseAnalysisRun.id))
            .where(CaseAnalysisRun.status.in_({"queued", "processing"}))
            .group_by(CaseAnalysisRun.status)
        ).all())
        summaries = dict(db.execute(
            select(CaseSummaryRun.status, func.count(CaseSummaryRun.id))
            .where(CaseSummaryRun.status.in_({"queued", "processing"}))
            .group_by(CaseSummaryRun.status)
        ).all())
        graphs = dict(db.execute(
            select(CaseKnowledgeGraphRun.status, func.count(CaseKnowledgeGraphRun.id))
            .where(CaseKnowledgeGraphRun.status.in_({"queued", "processing"}))
            .group_by(CaseKnowledgeGraphRun.status)
        ).all())
    return {
        "enabled": enabled,
        "running": worker["running"] if enabled else False,
        "current_task": worker["current_task"] if enabled else None,
        "last_completed_at": worker["last_completed_at"] if enabled else None,
        "last_error": worker["last_error"] if enabled else None,
        "pending": {
            "documents": documents,
            "analysis": analysis,
            "summaries": summaries,
            "knowledge_graphs": graphs,
        },
    }
