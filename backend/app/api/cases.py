from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db, lock_case_for_update
from app.db.models import (
    Case,
    CaseAnalysisRun,
    CaseDocument,
    CaseDeadline,
    CaseAnalysisFinding,
    CaseKnowledgeGraphRun,
    CaseSummaryRun,
    DocumentTextUnit,
)
from app.schemas.cases import (
    CaseCreate,
    CaseDocumentRead,
    CaseRead,
    CaseUpdate,
    CaseDocumentUpdate,
    FindingReviewUpdate,
    DocumentTextUnitRead,
    UploadBatchResult,
    UploadRejection,
)
from app.services.uploads import UploadRejected, save_upload
from app.services.document_processing import process_document_in_background
from app.services.knowledge_graph_processing import delete_case_knowledge_graph
from app.services.document_similarity import find_near_duplicate_documents


router = APIRouter(prefix="/cases", tags=["cases"])


def _assert_case_jobs_idle(db: Session, case_id: UUID) -> None:
    active = (
        (db.scalar(select(func.count(CaseAnalysisRun.id)).where(
            CaseAnalysisRun.case_id == case_id,
            CaseAnalysisRun.status.in_({"queued", "processing"}),
        )) or 0)
        + (db.scalar(select(func.count(CaseSummaryRun.id)).where(
            CaseSummaryRun.case_id == case_id,
            CaseSummaryRun.status.in_({"queued", "processing"}),
        )) or 0)
        + (db.scalar(select(func.count(CaseKnowledgeGraphRun.id)).where(
            CaseKnowledgeGraphRun.case_id == case_id,
            CaseKnowledgeGraphRun.status.in_({"queued", "processing"}),
        )) or 0)
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for case analysis, summary, and graph processing to finish before changing the case documents.",
        )


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> Case:
    case = Case(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("", response_model=list[CaseRead])
def list_cases(db: Session = Depends(get_db)) -> list[CaseRead]:
    cases = list(db.scalars(select(Case).order_by(Case.updated_at.desc())).all())
    if not cases:
        return []
    case_ids = [case.id for case in cases]
    ranked_runs = (
        select(
            CaseAnalysisRun.id.label("run_id"),
            func.row_number().over(
                partition_by=CaseAnalysisRun.case_id,
                order_by=(CaseAnalysisRun.created_at.desc(), CaseAnalysisRun.id.desc()),
            ).label("row_number"),
        )
        .where(CaseAnalysisRun.case_id.in_(case_ids))
        .subquery()
    )
    latest_runs = db.scalars(
        select(CaseAnalysisRun)
        .join(ranked_runs, CaseAnalysisRun.id == ranked_runs.c.run_id)
        .where(ranked_runs.c.row_number == 1)
    ).all()
    latest_run_by_case = {run.case_id: run for run in latest_runs}
    source_attention_by_case = dict(db.execute(
        select(CaseDocument.case_id, func.count(CaseDocument.id))
        .where(CaseDocument.case_id.in_(case_ids), CaseDocument.processing_status.in_({"failed", "needs_review"}))
        .group_by(CaseDocument.case_id)
    ).all())
    latest_upload_by_case = dict(db.execute(
        select(CaseDocument.case_id, func.max(CaseDocument.uploaded_at))
        .where(CaseDocument.case_id.in_(case_ids))
        .group_by(CaseDocument.case_id)
    ).all())
    completed_run_ids = [run.id for run in latest_runs if run.status == "completed"]
    open_findings_by_run = dict(db.execute(
        select(CaseAnalysisFinding.analysis_run_id, func.count(CaseAnalysisFinding.id))
        .where(
            CaseAnalysisFinding.analysis_run_id.in_(completed_run_ids),
            CaseAnalysisFinding.review_status.in_({"needs_review", "possible_contradiction"}),
        )
        .group_by(CaseAnalysisFinding.analysis_run_id)
    ).all()) if completed_run_ids else {}
    deadline_attention_by_case = dict(db.execute(
        select(CaseDeadline.case_id, func.count(CaseDeadline.id))
        .where(
            CaseDeadline.case_id.in_(case_ids),
            CaseDeadline.status == "open",
            CaseDeadline.due_date <= datetime.now(ZoneInfo(settings.case_timezone)).date() + timedelta(days=7),
        )
        .group_by(CaseDeadline.case_id)
    ).all())

    dashboard: list[CaseRead] = []
    for case in cases:
        latest_run = latest_run_by_case.get(case.id)
        source_attention = source_attention_by_case.get(case.id, 0)
        latest_upload = latest_upload_by_case.get(case.id)
        stale_upload_attention = int(bool(latest_run and latest_run.status == "completed" and latest_upload and latest_upload > (latest_run.completed_at or latest_run.created_at)))
        open_findings = open_findings_by_run.get(latest_run.id, 0) if latest_run is not None else 0
        item = CaseRead.model_validate(case)
        deadline_attention = deadline_attention_by_case.get(case.id, 0)
        dashboard.append(item.model_copy(update={
            "analysis_status": "new documents · re-analysis suggested" if stale_upload_attention else latest_run.status if latest_run else None,
            "attention_count": source_attention + open_findings + stale_upload_attention + deadline_attention,
            "deadline_attention_count": deadline_attention,
        }))
    return dashboard


@router.get("/{case_id}", response_model=CaseRead)
def get_case(case_id: UUID, db: Session = Depends(get_db)) -> CaseRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    
    latest_run = db.scalar(
        select(CaseAnalysisRun)
        .where(CaseAnalysisRun.case_id == case_id)
        .order_by(CaseAnalysisRun.created_at.desc(), CaseAnalysisRun.id.desc())
        .limit(1)
    )
    source_attention = db.scalar(
        select(func.count(CaseDocument.id))
        .where(CaseDocument.case_id == case_id, CaseDocument.processing_status.in_({"failed", "needs_review"}))
    ) or 0
    latest_upload = db.scalar(
        select(func.max(CaseDocument.uploaded_at))
        .where(CaseDocument.case_id == case_id)
    )
    stale_upload_attention = int(bool(
        latest_run and latest_run.status == "completed" and latest_upload and latest_upload > (latest_run.completed_at or latest_run.created_at)
    ))
    open_findings = 0
    if latest_run and latest_run.status == "completed":
        open_findings = db.scalar(
            select(func.count(CaseAnalysisFinding.id))
            .where(
                CaseAnalysisFinding.analysis_run_id == latest_run.id,
                CaseAnalysisFinding.review_status.in_({"needs_review", "possible_contradiction"}),
            )
        ) or 0
    
    deadline_attention = db.scalar(
        select(func.count(CaseDeadline.id))
        .where(
            CaseDeadline.case_id == case_id,
            CaseDeadline.status == "open",
            CaseDeadline.due_date <= datetime.now(ZoneInfo(settings.case_timezone)).date() + timedelta(days=7),
        )
    ) or 0

    item = CaseRead.model_validate(case)
    return item.model_copy(update={
        "analysis_status": "new documents · re-analysis suggested" if stale_upload_attention else latest_run.status if latest_run else None,
        "attention_count": source_attention + open_findings + stale_upload_attention + deadline_attention,
        "deadline_attention_count": deadline_attention,
    })


@router.patch("/{case_id}", response_model=CaseRead)
def update_case(
    case_id: UUID, payload: CaseUpdate, db: Session = Depends(get_db)
) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: UUID, db: Session = Depends(get_db)) -> Response:
    case = lock_case_for_update(db, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    documents = list(db.scalars(
        select(CaseDocument).where(CaseDocument.case_id == case_id)
        .order_by(CaseDocument.id).with_for_update()
    ).all())
    if any(document.processing_status in {"queued", "processing"} for document in documents):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for document processing to finish before deleting this case.",
        )
    active_runs = (
        (db.scalar(select(func.count(CaseAnalysisRun.id)).where(CaseAnalysisRun.case_id == case_id, CaseAnalysisRun.status.in_({"queued", "processing"}))) or 0)
        + (db.scalar(select(func.count(CaseSummaryRun.id)).where(CaseSummaryRun.case_id == case_id, CaseSummaryRun.status.in_({"queued", "processing"}))) or 0)
        + (db.scalar(select(func.count(CaseKnowledgeGraphRun.id)).where(CaseKnowledgeGraphRun.case_id == case_id, CaseKnowledgeGraphRun.status.in_({"queued", "processing"}))) or 0)
    )
    if active_runs:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for case analysis, summary, and graph processing to finish before deleting this case.")
    storage_keys = [document.storage_key for document in documents]
    has_graph = bool(db.scalar(select(func.count(CaseKnowledgeGraphRun.id)).where(CaseKnowledgeGraphRun.case_id == case_id)) or 0)
    if has_graph:
        delete_case_knowledge_graph(case_id)
    db.delete(case)
    db.commit()
    if has_graph:
        # A graph worker may have finished its Neo4j write while this case was
        # being deleted. Sweep once more after the relational cascade commits.
        delete_case_knowledge_graph(case_id)

    storage_root = settings.uploads_dir.resolve()
    for storage_key in storage_keys:
        path = (storage_root / storage_key).resolve()
        if path.is_relative_to(storage_root):
            path.unlink(missing_ok=True)
    case_directory = (storage_root / str(case_id)).resolve()
    if case_directory.is_relative_to(storage_root) and case_directory.is_dir():
        try:
            case_directory.rmdir()
        except OSError:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{case_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_document(case_id: UUID, document_id: UUID, db: Session = Depends(get_db)) -> Response:
    if lock_case_for_update(db, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    _assert_case_jobs_idle(db, case_id)
    document = db.scalar(
        select(CaseDocument)
        .options(selectinload(CaseDocument.text_units))
        .where(CaseDocument.id == document_id, CaseDocument.case_id == case_id)
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.processing_status in {"queued", "processing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for document processing to finish before deleting it.")
    storage_key = document.storage_key
    # Removing a source invalidates case-wide results whose citations may point
    # into that source, so clear derived runs and require a fresh analysis.
    has_graph = bool(db.scalar(select(func.count(CaseKnowledgeGraphRun.id)).where(CaseKnowledgeGraphRun.case_id == case_id)) or 0)
    if has_graph:
        delete_case_knowledge_graph(case_id)
    db.execute(delete(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id))
    db.execute(delete(CaseSummaryRun).where(CaseSummaryRun.case_id == case_id))
    db.delete(document)
    db.commit()
    if has_graph:
        delete_case_knowledge_graph(case_id)
    storage_root = settings.uploads_dir.resolve()
    path = (storage_root / storage_key).resolve()
    if path.is_relative_to(storage_root):
        path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{case_id}/documents", response_model=list[CaseDocumentRead])
def list_case_documents(case_id: UUID, db: Session = Depends(get_db)) -> list[CaseDocumentRead]:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    documents = list(
        db.scalars(
            select(CaseDocument)
            .where(CaseDocument.case_id == case_id)
            .order_by(CaseDocument.uploaded_at.desc())
        ).all()
    )
    stats = {row.document_id: row for row in db.execute(
        select(
            DocumentTextUnit.document_id.label("document_id"),
            func.count(DocumentTextUnit.id).label("unit_count"),
            func.sum(case((DocumentTextUnit.character_count > 0, 1), else_=0)).label("readable_count"),
            func.sum(case((DocumentTextUnit.character_count == 0, 1), else_=0)).label("unreadable_count"),
            func.count(func.distinct(DocumentTextUnit.page_number)).label("page_count"),
            func.count(func.distinct(case((DocumentTextUnit.character_count > 0, DocumentTextUnit.page_number), else_=None))).label("pages_with_text"),
            func.sum(case((
                ((DocumentTextUnit.ocr_confidence.is_not(None)) | func.lower(DocumentTextUnit.extraction_method).like("%ocr%"))
                & ((DocumentTextUnit.ocr_confidence.is_(None)) | (DocumentTextUnit.ocr_confidence < settings.ocr_review_confidence_threshold)), 1
            ), else_=0)).label("review_count"),
        ).join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
        .where(CaseDocument.case_id == case_id)
        .group_by(DocumentTextUnit.document_id)
    ).all()}
    results = []
    for document in documents:
        values = stats.get(document.id)
        results.append(CaseDocumentRead.model_validate({
            "id": document.id, "case_id": document.case_id,
            "original_filename": document.original_filename, "content_type": document.content_type,
            "file_extension": document.file_extension, "size_bytes": document.size_bytes,
            "sha256": document.sha256, "processing_status": document.processing_status,
            "extraction_error": document.extraction_error, "description": document.description,
            "document_type": document.document_type, "uploaded_at": document.uploaded_at,
            "text_unit_count": getattr(values, "unit_count", 0) or 0,
            "readable_location_count": getattr(values, "readable_count", 0) or 0,
            "unreadable_location_count": getattr(values, "unreadable_count", 0) or 0,
            "page_count": getattr(values, "page_count", 0) or 0,
            "pages_with_text_count": getattr(values, "pages_with_text", 0) or 0,
            "pages_without_text_count": max((getattr(values, "page_count", 0) or 0) - (getattr(values, "pages_with_text", 0) or 0), 0),
            "review_location_count": getattr(values, "review_count", 0) or 0,
            "near_duplicate_matches": [],
        }))
    return results


@router.get("/{case_id}/documents/near-duplicates")
def find_case_near_duplicates(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    documents = list(db.scalars(
        select(CaseDocument).options(selectinload(CaseDocument.text_units))
        .where(CaseDocument.case_id == case_id, CaseDocument.processing_status == "processed")
        .order_by(CaseDocument.uploaded_at.desc())
    ).all())
    matches = find_near_duplicate_documents([
        (document.id, document.original_filename, "\n".join(unit.text for unit in document.text_units if unit.text.strip()))
        for document in documents
    ])
    return {str(document_id): items for document_id, items in matches.items()}


@router.get(
    "/{case_id}/documents/{document_id}/text",
    response_model=list[DocumentTextUnitRead],
)
def get_document_text(
    case_id: UUID, document_id: UUID, db: Session = Depends(get_db)
) -> list[DocumentTextUnit]:
    document = db.scalar(
        select(CaseDocument).where(
            CaseDocument.id == document_id, CaseDocument.case_id == case_id
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return list(
        db.scalars(
            select(DocumentTextUnit)
            .where(DocumentTextUnit.document_id == document_id)
            .order_by(DocumentTextUnit.unit_number)
        ).all()
    )


@router.post(
    "/{case_id}/documents",
    response_model=UploadBatchResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_case_documents(
    case_id: UUID,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadBatchResult:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    if len(files) > settings.max_upload_files_per_batch:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload no more than {settings.max_upload_files_per_batch} files per batch.",
        )

    uploaded: list[CaseDocument] = []
    rejected: list[UploadRejection] = []

    for upload in files:
        filename = upload.filename or "(unnamed file)"
        stored_path: Path | None = None
        # Serialize quota checks and file registration with other uploads and
        # case deletion. Re-read usage while holding the case row lock so two
        # simultaneous requests cannot both spend the same remaining quota.
        case = lock_case_for_update(db, case_id)
        if case is None:
            await upload.close()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
        try:
            _assert_case_jobs_idle(db, case_id)
        except HTTPException:
            db.rollback()
            await upload.close()
            raise
        accepted_count = db.scalar(
            select(func.count(CaseDocument.id)).where(CaseDocument.case_id == case_id)
        ) or 0
        accepted_bytes = db.scalar(
            select(func.coalesce(func.sum(CaseDocument.size_bytes), 0)).where(CaseDocument.case_id == case_id)
        ) or 0
        if accepted_count >= settings.max_case_documents:
            rejected.append(UploadRejection(filename=filename, reason="This case has reached its document-count limit."))
            db.rollback()
            await upload.close()
            continue
        remaining_bytes = settings.max_case_storage_bytes - accepted_bytes
        if remaining_bytes <= 0:
            rejected.append(UploadRejection(filename=filename, reason="This case has reached its storage limit."))
            db.rollback()
            await upload.close()
            continue
        try:
            filename, content_type, size_bytes, sha256, storage_key = await save_upload(
                upload, case_id, remaining_bytes
            )
            duplicate = db.scalar(
                select(CaseDocument).where(
                    CaseDocument.case_id == case_id,
                    CaseDocument.sha256 == sha256,
                )
            )
            stored_path = settings.uploads_dir / storage_key
            if duplicate is not None:
                stored_path.unlink(missing_ok=True)
                rejected.append(
                    UploadRejection(filename=filename, reason="This file is already in the case.")
                )
                continue

            document = CaseDocument(
                case_id=case_id,
                original_filename=filename,
                content_type=content_type,
                file_extension=Path(filename).suffix.lower(),
                size_bytes=size_bytes,
                sha256=sha256,
                storage_key=storage_key,
                processing_status="uploaded",
            )
            db.add(document)
            case.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(document)
            uploaded.append(document)
            if settings.app_env.strip().lower() == "test":
                background_tasks.add_task(process_document_in_background, document.id)
        except UploadRejected as error:
            db.rollback()
            rejected.append(UploadRejection(filename=filename, reason=str(error)))
        except IntegrityError:
            db.rollback()
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)
            rejected.append(
                UploadRejection(filename=filename, reason="This file is already in the case.")
            )
        except Exception:
            db.rollback()
            if stored_path is not None:
                stored_path.unlink(missing_ok=True)
            rejected.append(
                UploadRejection(filename=filename, reason="The file could not be stored.")
            )

    if not uploaded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"uploaded": [], "rejected": [item.model_dump() for item in rejected]},
        )

    return UploadBatchResult(uploaded=uploaded, rejected=rejected)


@router.post(
    "/{case_id}/documents/{document_id}/extract",
    response_model=CaseDocumentRead,
)
def retry_document_extraction(
    case_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> CaseDocument:
    if lock_case_for_update(db, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    _assert_case_jobs_idle(db, case_id)
    document = db.scalar(
        select(CaseDocument).where(
            CaseDocument.id == document_id, CaseDocument.case_id == case_id
        ).with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.processing_status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is already being processed.",
        )
    if document.processing_status == "queued":
        return document
    document.processing_status = "queued"
    document.extraction_error = None
    db.commit()
    db.refresh(document)
    if settings.app_env.strip().lower() == "test":
        background_tasks.add_task(process_document_in_background, document.id)
    return document


@router.patch("/{case_id}/documents/{document_id}", response_model=CaseDocumentRead)
def update_case_document(
    case_id: UUID, document_id: UUID, payload: CaseDocumentUpdate, db: Session = Depends(get_db)
) -> CaseDocument:
    document = db.scalar(
        select(CaseDocument)
        .where(CaseDocument.id == document_id, CaseDocument.case_id == case_id)
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    db.commit()
    db.refresh(document)
    return document


@router.put("/{case_id}/documents/{document_id}/file", response_model=CaseDocumentRead)
async def replace_case_document(
    case_id: UUID, document_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> CaseDocument:
    if lock_case_for_update(db, case_id) is None:
        await file.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    try:
        _assert_case_jobs_idle(db, case_id)
    except HTTPException:
        db.rollback()
        await file.close()
        raise
    document = db.scalar(select(CaseDocument).where(CaseDocument.id == document_id, CaseDocument.case_id == case_id).with_for_update())
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.processing_status in {"queued", "processing"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Wait for document processing to finish before replacing it.")
    old_key = document.storage_key
    storage_root = settings.uploads_dir.resolve()
    old_path = (storage_root / old_key).resolve()
    replacement_path: Path | None = None
    try:
        case_bytes = db.scalar(select(func.coalesce(func.sum(CaseDocument.size_bytes), 0)).where(CaseDocument.case_id == case_id)) or 0
        filename, content_type, size_bytes, sha256, storage_key = await save_upload(file, case_id, max(settings.max_case_storage_bytes - (case_bytes - document.size_bytes), 0))
        duplicate = db.scalar(select(CaseDocument).where(CaseDocument.case_id == case_id, CaseDocument.sha256 == sha256, CaseDocument.id != document_id))
        replacement_path = (storage_root / storage_key).resolve()
        if duplicate is not None:
            replacement_path.unlink(missing_ok=True)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That file is already attached to this case.")
        has_graph = bool(db.scalar(select(func.count(CaseKnowledgeGraphRun.id)).where(CaseKnowledgeGraphRun.case_id == case_id)) or 0)
        if has_graph:
            delete_case_knowledge_graph(case_id)
        db.execute(delete(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id))
        db.execute(delete(CaseSummaryRun).where(CaseSummaryRun.case_id == case_id))
        db.execute(delete(DocumentTextUnit).where(DocumentTextUnit.document_id == document_id))
        document.original_filename = filename
        document.content_type = content_type
        document.file_extension = Path(filename).suffix.lower()
        document.size_bytes = size_bytes
        document.sha256 = sha256
        document.storage_key = storage_key
        document.processing_status = "queued"
        document.extraction_error = None
        document.uploaded_at = datetime.now(timezone.utc)
        db.commit()
        if has_graph:
            delete_case_knowledge_graph(case_id)
        db.refresh(document)
        if old_path.is_relative_to(storage_root):
            old_path.unlink(missing_ok=True)
        return document
    except HTTPException:
        raise
    except UploadRejected as error:
        if replacement_path is not None:
            replacement_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception:
        db.rollback()
        if replacement_path is not None:
            replacement_path.unlink(missing_ok=True)
        raise


@router.get("/{case_id}/documents/{document_id}/file")
def get_case_document_file(
    case_id: UUID, document_id: UUID, db: Session = Depends(get_db)
) -> Response:
    document = db.scalar(
        select(CaseDocument).where(
            CaseDocument.id == document_id, CaseDocument.case_id == case_id
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    storage_root = settings.uploads_dir.resolve()
    file_path = (storage_root / document.storage_key).resolve()
    if not file_path.is_relative_to(storage_root) or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on disk.")

    from app.core.encryption import decrypt_bytes
    try:
        decrypted_content = decrypt_bytes(file_path.read_bytes())
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not decrypt document file.")

    return Response(
        content=decrypted_content,
        media_type=document.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"'
        },
    )



@router.patch("/{case_id}/analysis/findings/{finding_id}", response_model=dict[str, str | None])
def review_case_finding(
    case_id: UUID, finding_id: UUID, payload: FindingReviewUpdate, db: Session = Depends(get_db)
) -> dict[str, str | None]:
    finding = db.scalar(
        select(CaseAnalysisFinding)
        .join(CaseAnalysisRun, CaseAnalysisFinding.analysis_run_id == CaseAnalysisRun.id)
        .where(CaseAnalysisFinding.id == finding_id, CaseAnalysisRun.case_id == case_id)
    )
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found in this case.")
    if finding.analysis_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wait for this analysis to finish before reviewing its findings.",
        )
    finding.review_status = payload.review_status
    finding.review_note = payload.review_note
    db.commit()
    return {"id": str(finding.id), "review_status": finding.review_status, "review_note": finding.review_note}
