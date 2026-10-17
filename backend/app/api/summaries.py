from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, lock_case_for_update
from app.db.models import Case, CaseDocument, CaseSummaryRun, DocumentTextUnit
from app.schemas.cases import CaseSummaryRead, CaseSummaryRunRead, CaseSummaryStartRequest
from app.services.case_analysis_processing import gemini_is_ready, gemini_readiness_message
from app.services.summary_processing import process_case_summary


router = APIRouter(prefix="/cases", tags=["case-summaries"])


@router.post(
    "/{case_id}/summary",
    response_model=CaseSummaryRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_case_summary(
    case_id: UUID,
    background_tasks: BackgroundTasks,
    request: CaseSummaryStartRequest | None = None,
    db: Session = Depends(get_db),
) -> CaseSummaryRun:
    case = lock_case_for_update(db, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    active_run = db.scalar(select(CaseSummaryRun).where(
        CaseSummaryRun.case_id == case_id,
        CaseSummaryRun.status.in_({"queued", "processing"}),
    ).order_by(CaseSummaryRun.created_at.desc()).limit(1))
    if active_run is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A case summary is already queued or running.")
    if not gemini_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=gemini_readiness_message(),
        )
    documents = list(db.scalars(select(CaseDocument).where(CaseDocument.case_id == case_id)).all())
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload and extract case documents before generating a summary.",
        )
    pending_count = sum(
        document.processing_status in {"uploaded", "queued", "processing"}
        for document in documents
    )
    if pending_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Wait for extraction to finish for {pending_count} document(s), then retry.",
        )
    incomplete_documents = [
        document for document in documents
        if document.processing_status in {"failed", "needs_review"}
    ]
    if incomplete_documents and not (request and request.acknowledge_incomplete_sources):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "incomplete_sources_acknowledgement_required",
                "message": "Some documents failed extraction or need review. Retry or inspect them; to continue with readable content only, explicitly acknowledge the incomplete sources.",
                "documents": [document.original_filename for document in incomplete_documents],
            },
        )
    text_unit_count = db.scalar(
        select(func.count(DocumentTextUnit.id))
        .join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
        .where(CaseDocument.case_id == case_id, DocumentTextUnit.text != "")
    ) or 0
    if not text_unit_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extracted text is available in this case yet.",
        )

    run = CaseSummaryRun(
        case_id=case_id,
        status="queued",
        provider="google_gemini",
        model=settings.gemini_model,
        document_count=len(documents),
        text_unit_count=text_unit_count,
        incomplete_sources_acknowledged=bool(incomplete_documents),
    )
    db.add(run)
    case.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    if settings.app_env.strip().lower() == "test":
        background_tasks.add_task(process_case_summary, run.id)
    return run


@router.get("/{case_id}/summary/latest", response_model=CaseSummaryRead)
def latest_case_summary(case_id: UUID, db: Session = Depends(get_db)) -> CaseSummaryRead:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    run = db.scalar(
        select(CaseSummaryRun)
        .where(CaseSummaryRun.case_id == case_id)
        .order_by(CaseSummaryRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No summary run exists for this case.")
    return CaseSummaryRead(
        run=run,
        narrative_summary=run.narrative_summary,
        structured_summary=run.structured_summary,
    )
