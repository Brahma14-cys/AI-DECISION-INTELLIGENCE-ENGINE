from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, lock_case_for_update
from app.db.models import Case, CaseAnalysisRun, CaseDocument, CaseKnowledgeGraphRun
from app.schemas.cases import (
    CaseKnowledgeGraphRead,
    CaseKnowledgeGraphRunRead,
    CaseKnowledgeGraphSearchRead,
    CaseKnowledgeGraphSearchRequest,
)
from app.services.case_analysis_processing import gemini_is_ready, gemini_readiness_message
from app.services.knowledge_graph_processing import (
    graph_is_configured,
    process_case_knowledge_graph,
    search_case_knowledge_graph,
)


router = APIRouter(prefix="/cases", tags=["case-knowledge-graph"])


@router.post(
    "/{case_id}/knowledge-graph",
    response_model=CaseKnowledgeGraphRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_case_knowledge_graph(
    case_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CaseKnowledgeGraphRun:
    if lock_case_for_update(db, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    if not graph_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The case knowledge graph is not configured. Start Neo4j, set its credentials, and enable KNOWLEDGE_GRAPH_ENABLED.",
        )
    if not gemini_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=gemini_readiness_message(),
        )

    analysis_run = db.scalar(
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case_id, CaseAnalysisRun.status == "completed")
        .order_by(CaseAnalysisRun.created_at.desc())
        .limit(1)
    )
    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete Module 2 case analysis before building its knowledge graph.",
        )
    latest_upload = db.scalar(
        select(func.max(CaseDocument.uploaded_at)).where(CaseDocument.case_id == case_id)
    )
    if latest_upload and analysis_run.created_at < latest_upload:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="New documents were added after the latest Module 2 analysis. Re-run case analysis before building the knowledge graph.",
        )

    active_run = db.scalar(
        select(CaseKnowledgeGraphRun)
        .where(
            CaseKnowledgeGraphRun.case_id == case_id,
            CaseKnowledgeGraphRun.analysis_run_id == analysis_run.id,
            CaseKnowledgeGraphRun.status.in_({"queued", "processing"}),
        )
        .order_by(CaseKnowledgeGraphRun.created_at.desc())
        .limit(1)
    )
    if active_run is not None:
        return active_run

    run = CaseKnowledgeGraphRun(
        case_id=case_id,
        analysis_run_id=analysis_run.id,
        status="queued",
        provider="neo4j",
        embedding_model=settings.graph_embedding_model,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    if settings.app_env.strip().lower() == "test":
        background_tasks.add_task(process_case_knowledge_graph, run.id)
    return run


@router.get("/{case_id}/knowledge-graph/latest", response_model=CaseKnowledgeGraphRead)
def latest_case_knowledge_graph(case_id: UUID, db: Session = Depends(get_db)) -> CaseKnowledgeGraphRead:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    run = db.scalar(
        select(CaseKnowledgeGraphRun)
        .where(CaseKnowledgeGraphRun.case_id == case_id)
        .order_by(CaseKnowledgeGraphRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No knowledge graph run exists for this case.")
    latest_upload = db.scalar(
        select(func.max(CaseDocument.uploaded_at)).where(CaseDocument.case_id == case_id)
    )
    latest_analysis = db.scalar(
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case_id, CaseAnalysisRun.status == "completed")
        .order_by(CaseAnalysisRun.created_at.desc())
        .limit(1)
    )
    graph_run = CaseKnowledgeGraphRunRead.model_validate(run)
    if run.status == "completed" and (
        (latest_upload and run.analysis_run.created_at < latest_upload)
        or (latest_analysis is not None and latest_analysis.id != run.analysis_run_id)
    ):
        graph_run.status = "stale"
    snapshot = run.graph_snapshot or {}
    return CaseKnowledgeGraphRead(
        run=graph_run,
        nodes=snapshot.get("nodes", []),
        edges=snapshot.get("edges", []),
        capabilities=snapshot.get("capabilities", {}),
    )


@router.post(
    "/{case_id}/knowledge-graph/search",
    response_model=CaseKnowledgeGraphSearchRead,
)
def search_case_graph(
    case_id: UUID,
    request: CaseKnowledgeGraphSearchRequest,
    db: Session = Depends(get_db),
) -> CaseKnowledgeGraphSearchRead:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    run = db.scalar(
        select(CaseKnowledgeGraphRun)
        .where(CaseKnowledgeGraphRun.case_id == case_id, CaseKnowledgeGraphRun.status == "completed")
        .order_by(CaseKnowledgeGraphRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Build the case knowledge graph before searching it.",
        )
    latest_analysis = db.scalar(
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case_id, CaseAnalysisRun.status == "completed")
        .order_by(CaseAnalysisRun.created_at.desc())
        .limit(1)
    )
    latest_upload = db.scalar(
        select(func.max(CaseDocument.uploaded_at)).where(CaseDocument.case_id == case_id)
    )
    if (
        latest_analysis is None
        or latest_analysis.id != run.analysis_run_id
        or (latest_upload and latest_analysis.created_at < latest_upload)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The graph is stale. Re-run case analysis and rebuild the knowledge graph before searching.",
        )
    if not graph_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The case knowledge graph is not configured.",
        )
    try:
        results, truncated = search_case_knowledge_graph(
            case_id, run.id, request.query, request.top_k
        )
    except Exception as error:  # noqa: BLE001 — do not expose driver/model diagnostics to the API client.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph search is temporarily unavailable. Check Neo4j connectivity and graph status.",
        ) from error
    return CaseKnowledgeGraphSearchRead(
        case_id=case_id,
        graph_run_id=run.id,
        query=request.query,
        results=results,
        search_truncated=truncated,
    )
