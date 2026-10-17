from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.core.database import get_db, lock_case_for_update
from app.db.models import (
    Case,
    CaseAnalysisFact,
    CaseAnalysisFinding,
    CaseAnalysisExtractionItem,
    CaseAnalysisReview,
    CaseAnalysisRun,
    CaseClaimReview,
    CaseClaimReviewEvidence,
    CaseDocument,
    DocumentTextUnit,
)
from app.schemas.cases import (
    CaseAnalysisAvailability,
    CaseAnalysisRead,
    CaseAnalysisRunRead,
    CaseAnalysisStartRequest,
    AnalysisReviewUpdate,
    CaseAnalysisReviewRead,
)
from app.services.case_analysis_processing import (
    gemini_is_ready,
    gemini_readiness_message,
    process_case_analysis,
)


router = APIRouter(prefix="/cases", tags=["case-analysis"])


@router.get("/{case_id}/analysis/config", response_model=CaseAnalysisAvailability)
def analysis_configuration(case_id: UUID, db: Session = Depends(get_db)) -> CaseAnalysisAvailability:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return CaseAnalysisAvailability(
        ready=gemini_is_ready(),
        model=settings.gemini_model,
        message=gemini_readiness_message(),
    )


@router.get("/{case_id}/analysis/changes")
def case_analysis_changes(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    runs = list(db.scalars(
        select(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id, CaseAnalysisRun.status == "completed")
        .order_by(CaseAnalysisRun.created_at.desc()).limit(2)
        .options(
            selectinload(CaseAnalysisRun.facts).joinedload(CaseAnalysisFact.source_unit).joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.findings).joinedload(CaseAnalysisFinding.left_fact).joinedload(CaseAnalysisFact.source_unit).joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.findings).joinedload(CaseAnalysisFinding.right_fact).joinedload(CaseAnalysisFact.source_unit).joinedload(DocumentTextUnit.document),
        )
    ).all())
    if not runs:
        return {"latest_run_at": None, "previous_run_at": None, "new_facts": [], "new_findings": [], "resolved_findings": [], "documents_since_previous_run": []}
    latest = runs[0]
    previous = runs[1] if len(runs) > 1 else None
    def fact_signature(fact: CaseAnalysisFact) -> tuple[str, str]:
        return (fact.statement.casefold().strip(), str(fact.source_unit.document_id))
    def finding_signature(finding: CaseAnalysisFinding) -> tuple[str, str, str]:
        sides = sorted((finding.left_fact.statement.casefold().strip(), finding.right_fact.statement.casefold().strip()))
        return finding.finding_type, sides[0], sides[1]
    previous_facts = {fact_signature(fact) for fact in (previous.facts if previous else [])}
    new_facts = [fact for fact in latest.facts if fact_signature(fact) not in previous_facts] if previous else []
    previous_findings = {finding_signature(item): item for item in (previous.findings if previous else [])}
    latest_findings = {finding_signature(item): item for item in latest.findings}
    new_findings = [item for key, item in latest_findings.items() if key not in previous_findings] if previous else []
    resolved_findings = [item for key, item in previous_findings.items() if key not in latest_findings]
    latest_time = latest.completed_at or latest.created_at
    earlier_documents = list(db.scalars(
        select(CaseDocument).where(CaseDocument.case_id == case_id, CaseDocument.uploaded_at > (previous.completed_at or previous.created_at if previous else latest.created_at))
        .order_by(CaseDocument.uploaded_at)
    ).all())
    return {
        "latest_run_at": latest_time,
        "previous_run_at": (previous.completed_at or previous.created_at) if previous else None,
        "new_facts": [{"statement": item.statement, "filename": item.source_unit.document.original_filename, "document_id": item.source_unit.document_id, "locator": item.source_unit.locator_label, "page_num": item.source_unit.page_number, "quote": item.evidence_quote} for item in new_facts[:100]],
        "new_findings": [{"finding_type": item.finding_type, "explanation": item.explanation, "review_status": item.review_status, "left": {"statement": item.left_fact.statement, "filename": item.left_fact.source_unit.document.original_filename, "document_id": item.left_fact.source_unit.document_id, "locator": item.left_fact.source_unit.locator_label, "quote": item.left_fact.evidence_quote}, "right": {"statement": item.right_fact.statement, "filename": item.right_fact.source_unit.document.original_filename, "document_id": item.right_fact.source_unit.document_id, "locator": item.right_fact.source_unit.locator_label, "quote": item.right_fact.evidence_quote}} for item in new_findings[:100]],
        "resolved_findings": [{"finding_type": item.finding_type, "explanation": item.explanation, "left_statement": item.left_fact.statement, "right_statement": item.right_fact.statement} for item in resolved_findings[:100]],
        "documents_since_previous_run": [{"id": str(item.id), "filename": item.original_filename, "uploaded_at": item.uploaded_at} for item in earlier_documents],
    }


@router.post("/{case_id}/analysis", response_model=CaseAnalysisRunRead, status_code=status.HTTP_202_ACCEPTED)
def start_case_analysis(
    case_id: UUID,
    background_tasks: BackgroundTasks,
    request: CaseAnalysisStartRequest | None = None,
    db: Session = Depends(get_db),
) -> CaseAnalysisRun:
    case = lock_case_for_update(db, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    active_run = db.scalar(select(CaseAnalysisRun).where(
        CaseAnalysisRun.case_id == case_id,
        CaseAnalysisRun.status.in_({"queued", "processing"}),
    ).order_by(CaseAnalysisRun.created_at.desc()).limit(1))
    if active_run is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Case analysis is already queued or running.")
    if not gemini_is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=gemini_readiness_message(),
        )

    documents = list(db.scalars(select(CaseDocument).where(CaseDocument.case_id == case_id)).all())
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload and extract case documents before running analysis.",
        )
    pending_count = sum(document.processing_status in {"uploaded", "queued", "processing"} for document in documents)
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

    unit_count = db.scalar(
        select(func.count(DocumentTextUnit.id))
        .join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
        .where(CaseDocument.case_id == case_id, DocumentTextUnit.text != "")
    ) or 0
    if unit_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extracted text is available in this case yet.",
        )

    run = CaseAnalysisRun(
        case_id=case_id,
        status="queued",
        provider="google_gemini",
        model=settings.gemini_model,
        document_count=len(documents),
        text_unit_count=unit_count,
        advocate_claims=request.advocate_claims if request else [],
        incomplete_sources_acknowledged=bool(incomplete_documents),
    )
    db.add(run)
    case.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    if settings.app_env.strip().lower() == "test":
        background_tasks.add_task(process_case_analysis, run.id, request.advocate_claims if request else [])
    return run


@router.get("/{case_id}/analysis/latest", response_model=CaseAnalysisRead)
def latest_case_analysis(case_id: UUID, db: Session = Depends(get_db)) -> CaseAnalysisRead:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    query = (
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case_id)
        .order_by(CaseAnalysisRun.created_at.desc())
        .limit(1)
        .options(
            selectinload(CaseAnalysisRun.facts)
            .joinedload(CaseAnalysisFact.source_unit)
            .joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.findings)
            .joinedload(CaseAnalysisFinding.left_fact)
            .joinedload(CaseAnalysisFact.source_unit)
            .joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.extraction_items)
            .joinedload(CaseAnalysisExtractionItem.source_unit)
            .joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.findings)
            .joinedload(CaseAnalysisFinding.right_fact)
            .joinedload(CaseAnalysisFact.source_unit)
            .joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.claim_reviews)
            .joinedload(CaseClaimReview.source_fact)
            .joinedload(CaseAnalysisFact.source_unit)
            .joinedload(DocumentTextUnit.document),
            selectinload(CaseAnalysisRun.claim_reviews)
            .selectinload(CaseClaimReview.evidence)
            .joinedload(CaseClaimReviewEvidence.evidence_fact)
            .joinedload(CaseAnalysisFact.source_unit)
            .joinedload(DocumentTextUnit.document),
        )
    )
    run = db.scalar(query)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis run exists for this case.")
    return CaseAnalysisRead(
        run=run,
        facts=run.facts,
        extraction_items=run.extraction_items,
        findings=run.findings,
        claim_reviews=run.claim_reviews,
        advocate_reviews=list(db.scalars(select(CaseAnalysisReview).where(CaseAnalysisReview.analysis_run_id == run.id).order_by(CaseAnalysisReview.created_at)).all()),
    )


@router.get("/{case_id}/analysis/reviews", response_model=list[CaseAnalysisReviewRead])
def list_case_analysis_reviews(case_id: UUID, db: Session = Depends(get_db)) -> list[CaseAnalysisReview]:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    latest = db.scalar(select(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id).order_by(CaseAnalysisRun.created_at.desc()).limit(1))
    if latest is None:
        return []
    return list(db.scalars(select(CaseAnalysisReview).where(CaseAnalysisReview.analysis_run_id == latest.id).order_by(CaseAnalysisReview.created_at)).all())


@router.put("/{case_id}/analysis/{analysis_run_id}/reviews", response_model=CaseAnalysisReviewRead)
def save_case_analysis_review(
    case_id: UUID, analysis_run_id: UUID, payload: AnalysisReviewUpdate, db: Session = Depends(get_db)
) -> CaseAnalysisReview:
    run = db.scalar(select(CaseAnalysisRun).where(CaseAnalysisRun.id == analysis_run_id, CaseAnalysisRun.case_id == case_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found in this case.")
    if run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for this analysis to finish before reviewing its findings.",
        )
    model_by_kind = {
        "fact": CaseAnalysisFact,
        "extraction_item": CaseAnalysisExtractionItem,
        "finding": CaseAnalysisFinding,
        "claim_review": CaseClaimReview,
    }
    target_model = model_by_kind[payload.target_kind]
    target = db.scalar(select(target_model).where(target_model.id == payload.target_id, target_model.analysis_run_id == analysis_run_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review target not found in this analysis.")
    allowed_statuses = {
        "fact": {"confirmed", "corrected", "rejected", "needs_review"},
        "extraction_item": {"confirmed", "corrected", "rejected", "needs_review"},
        "finding": {"confirmed_contradiction", "possible_contradiction", "not_a_contradiction", "needs_review"},
        "claim_review": {"accepted", "disputed", "needs_review"},
    }
    if payload.status not in allowed_statuses[payload.target_kind]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported review status for this item.")
    if payload.status == "corrected" and not payload.correction_text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter the corrected text to save a correction.")
    review = db.scalar(select(CaseAnalysisReview).where(
        CaseAnalysisReview.analysis_run_id == analysis_run_id,
        CaseAnalysisReview.target_kind == payload.target_kind,
        CaseAnalysisReview.target_id == payload.target_id,
    ))
    if review is None:
        review = CaseAnalysisReview(case_id=case_id, analysis_run_id=analysis_run_id, target_kind=payload.target_kind, target_id=payload.target_id)
        db.add(review)
    review.status = payload.status
    review.correction_text = payload.correction_text
    review.correction_category = payload.correction_category
    review.note = payload.note
    if payload.target_kind == "finding":
        target.review_status = payload.status
        target.review_note = payload.note
    db.commit()
    db.refresh(review)
    return review
