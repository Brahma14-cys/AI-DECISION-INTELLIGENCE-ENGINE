import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.encryption import decrypt_bytes
from app.db.models import (
    CaseAnalysisRun,
    CaseDocument,
    CaseKnowledgeGraphRun,
    CaseSummaryRun,
    DocumentTextUnit,
)
from app.services.document_extraction import extract_document


logger = logging.getLogger(__name__)


def process_document_in_background(document_id: UUID) -> None:
    """Extract one document using a separate database session for background work."""
    with SessionLocal() as db:
        document = db.scalar(
            select(CaseDocument)
            .where(CaseDocument.id == document_id)
            .with_for_update()
        )
        if document is None:
            return

        document.processing_status = "processing"
        document.extraction_error = None
        db.commit()

        try:
            storage_root = settings.uploads_dir.resolve()
            source_path = (storage_root / document.storage_key).resolve()
            if not source_path.is_relative_to(storage_root) or not source_path.is_file():
                raise ValueError("The stored document could not be found.")

            plaintext = decrypt_bytes(source_path.read_bytes())
            result = extract_document(plaintext, document.file_extension)

            # Keep the last successful extraction until the new result has at
            # least as much readable coverage. Empty or worse retries cannot
            # erase source text that an advocate may already have reviewed.
            new_units = [
                DocumentTextUnit(
                    document_id=document_id,
                    unit_number=unit.unit_number,
                    page_number=unit.page_number,
                    locator_label=unit.locator_label,
                    text=unit.text,
                    character_count=len(unit.text),
                    extraction_method=unit.extraction_method,
                    ocr_confidence=unit.ocr_confidence,
                )
                for unit in result.units
            ]
            old_units = list(db.scalars(
                select(DocumentTextUnit)
                .where(DocumentTextUnit.document_id == document_id)
                .order_by(DocumentTextUnit.unit_number)
            ).all())
            result_signature = [
                (unit.unit_number, unit.page_number, unit.locator_label, unit.text,
                 unit.extraction_method, unit.ocr_confidence)
                for unit in new_units
            ]
            old_signature = [
                (unit.unit_number, unit.page_number, unit.locator_label, unit.text,
                 unit.extraction_method, unit.ocr_confidence)
                for unit in old_units
            ]
            extraction_changed = result_signature != old_signature
            old_quality = (
                sum(bool(unit.text.strip()) for unit in old_units),
                sum(len(unit.text.strip()) for unit in old_units),
            )
            new_quality = (
                sum(bool(unit.text.strip()) for unit in new_units),
                sum(len(unit.text.strip()) for unit in new_units),
            )
            replace_units = extraction_changed and (
                not old_units or (result.status != "failed" and new_quality >= old_quality)
            )

            if replace_units:
                case_id = document.case_id
                graph_exists = bool(db.scalar(
                    select(CaseKnowledgeGraphRun.id)
                    .where(CaseKnowledgeGraphRun.case_id == case_id)
                    .limit(1)
                ))
                if graph_exists:
                    # If Neo4j cleanup fails, preserve the old relational
                    # extraction and its analysis rather than swapping sources.
                    from app.services.knowledge_graph_processing import delete_case_knowledge_graph

                    delete_case_knowledge_graph(case_id)
                db.execute(delete(CaseAnalysisRun).where(CaseAnalysisRun.case_id == case_id))
                db.execute(delete(CaseSummaryRun).where(CaseSummaryRun.case_id == case_id))
                db.execute(delete(CaseKnowledgeGraphRun).where(CaseKnowledgeGraphRun.case_id == case_id))
                db.execute(delete(DocumentTextUnit).where(DocumentTextUnit.document_id == document_id))
                db.add_all(new_units)

            document.processing_status = result.status
            document.extraction_error = result.error
            db.commit()
            # Start the downstream case-wide analysis only after the last
            # uploaded document has completed extraction successfully.
            from app.services.case_workflow import enqueue_case_analysis_if_ready

            try:
                enqueue_case_analysis_if_ready(db, document.case_id)
            except Exception:  # noqa: BLE001 — extraction remains complete if downstream scheduling is temporarily unavailable.
                db.rollback()
                logger.exception("Could not queue the case analysis after successful document extraction.")
        except Exception as error:  # noqa: BLE001 — persist a useful status for the advocate.
            logger.error(
                "Document extraction failed document_id=%s error_type=%s",
                document_id,
                type(error).__name__,
            )
            db.rollback()
            failed_document = db.get(CaseDocument, document_id)
            if failed_document is not None:
                failed_document.processing_status = "failed"
                failed_document.extraction_error = (
                    str(error)
                    if isinstance(error, ValueError)
                    else "Processing failed. Check that local extraction tools are installed and retry."
                )
                db.commit()
