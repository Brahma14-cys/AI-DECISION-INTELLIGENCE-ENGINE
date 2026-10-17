from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import settings
from app.core import durable_worker
from app.core.database import get_db
from app.db.models import (
    CaseAnalysisRun,
    CaseDocument,
    CaseKnowledgeGraphRun,
    DocumentTextUnit,
)
from app.services import case_analysis_processing, knowledge_graph_processing
from app.services import document_processing
from app.services.document_extraction import ExtractionResult
from app.services.case_workflow import (
    enqueue_case_analysis_if_ready,
    enqueue_case_graph_after_analysis,
)


def _session_from_test_app():
    generator = get_db_override()
    return generator, next(generator)


def get_db_override():
    # conftest installs a test-only session provider for each client fixture.
    from app.main import app

    return app.dependency_overrides[get_db]()


def test_completed_uploads_queue_analysis_and_then_graph(client, docx_bytes, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "gemini_model", "test-model")
    monkeypatch.setattr(settings, "graph_embedding_model", "test-embedding")
    monkeypatch.setattr(case_analysis_processing, "gemini_is_ready", lambda: True)

    case = client.post("/api/v1/cases", json={"title": "Automatic workflow"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, UUID(uploaded["id"]))
        document.processing_status = "processed"
        db.add(DocumentTextUnit(
            document_id=document.id,
            unit_number=0,
            page_number=1,
            locator_label="Page 1",
            text="The notice was served on 12 March 2024.",
            character_count=38,
            extraction_method="digital_text",
        ))
        db.commit()

        assert enqueue_case_analysis_if_ready(db, document.case_id) is True
        assert enqueue_case_analysis_if_ready(db, document.case_id) is False
        analysis = db.scalar(select(CaseAnalysisRun).where(CaseAnalysisRun.case_id == document.case_id))
        assert analysis.status == "queued"
        assert analysis.incomplete_sources_acknowledged is False

        analysis.status = "completed"
        analysis.created_at = document.uploaded_at + timedelta(seconds=1)
        db.commit()
        monkeypatch.setattr(knowledge_graph_processing, "graph_is_configured", lambda: True)
        assert enqueue_case_graph_after_analysis(db, analysis) is True
        assert enqueue_case_graph_after_analysis(db, analysis) is False
        assert db.scalar(select(func.count(CaseKnowledgeGraphRun.id))) == 1
    finally:
        db.close()
        generator.close()


def test_worker_does_not_starve_older_analysis_behind_newer_upload(client, docx_bytes):
    case = client.post("/api/v1/cases", json={"title": "Fair queue"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, UUID(uploaded["id"]))
        document.processing_status = "queued"
        analysis = CaseAnalysisRun(
            case_id=document.case_id, status="queued", model="test-model",
            document_count=0, text_unit_count=0, advocate_claims=[],
        )
        db.add(analysis)
        db.flush()
        analysis.created_at = document.uploaded_at - timedelta(seconds=1)
        db.commit()

        claimed = durable_worker._claim_next_task()

        assert claimed is not None
        assert claimed[0] == "analysis"
        assert claimed[1] == analysis.id
    finally:
        db.close()
        generator.close()


def test_incomplete_document_does_not_auto_queue_analysis(client, docx_bytes, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(case_analysis_processing, "gemini_is_ready", lambda: True)
    case = client.post("/api/v1/cases", json={"title": "Review required"}).json()
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("unreadable.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert response.status_code == 201
    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, UUID(response.json()["uploaded"][0]["id"]))
        document.processing_status = "needs_review"
        db.commit()
        assert enqueue_case_analysis_if_ready(db, document.case_id) is False
        assert db.scalar(select(func.count(CaseAnalysisRun.id))) == 0
    finally:
        db.close()
        generator.close()


def test_successful_document_worker_automatically_queues_case_analysis(client, docx_bytes, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    case = client.post("/api/v1/cases", json={"title": "Upload-triggered analysis"}).json()
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert response.status_code == 201
    document_id = UUID(response.json()["uploaded"][0]["id"])

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "gemini_model", "test-model")
    monkeypatch.setattr(case_analysis_processing, "gemini_is_ready", lambda: True)
    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, document_id)
        document.processing_status = "queued"
        db.commit()
    finally:
        db.close()
        generator.close()

    document_processing.process_document_in_background(document_id)

    generator, db = _session_from_test_app()
    try:
        queued = db.scalars(select(CaseAnalysisRun).where(CaseAnalysisRun.case_id == UUID(case["id"]))).all()
        assert len(queued) == 1
        assert queued[0].status == "queued"
        assert queued[0].document_count == 1
        assert queued[0].text_unit_count > 0
    finally:
        db.close()
        generator.close()


def test_failed_extraction_retry_preserves_last_successful_text(client, docx_bytes, monkeypatch):
    case = client.post("/api/v1/cases", json={"title": "Retry preserves evidence"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    document_id = UUID(uploaded["id"])

    generator, db = _session_from_test_app()
    try:
        old_units = list(db.scalars(
            select(DocumentTextUnit).where(DocumentTextUnit.document_id == document_id)
        ).all())
        assert old_units
        old_unit_ids = {unit.id for unit in old_units}
    finally:
        db.close()
        generator.close()

    def fail_extraction(*_args, **_kwargs):
        raise RuntimeError("synthetic OCR failure")

    monkeypatch.setattr(document_processing, "extract_document", fail_extraction)
    document_processing.process_document_in_background(document_id)

    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, document_id)
        current_units = list(db.scalars(
            select(DocumentTextUnit).where(DocumentTextUnit.document_id == document_id)
        ).all())
        assert document.processing_status == "failed"
        assert {unit.id for unit in current_units} == old_unit_ids
        assert any("notice" in unit.text.casefold() for unit in current_units)
    finally:
        db.close()
        generator.close()


def test_retry_with_no_readable_output_keeps_previous_text(client, docx_bytes, monkeypatch):
    case = client.post("/api/v1/cases", json={"title": "Empty retry preserves evidence"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    document_id = UUID(uploaded["id"])

    generator, db = _session_from_test_app()
    try:
        previous_count = db.scalar(
            select(func.count(DocumentTextUnit.id)).where(DocumentTextUnit.document_id == document_id)
        )
        assert previous_count
    finally:
        db.close()
        generator.close()

    monkeypatch.setattr(
        document_processing,
        "extract_document",
        lambda *_args, **_kwargs: ExtractionResult([], "needs_review", "No readable text was found."),
    )
    document_processing.process_document_in_background(document_id)

    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, document_id)
        current_count = db.scalar(
            select(func.count(DocumentTextUnit.id)).where(DocumentTextUnit.document_id == document_id)
        )
        assert document.processing_status == "needs_review"
        assert current_count == previous_count
    finally:
        db.close()
        generator.close()

def test_document_delete_is_rejected_while_extraction_is_active(client, docx_bytes):
    case = client.post("/api/v1/cases", json={"title": "Active extraction lock"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    document_id = UUID(uploaded["id"])

    generator, db = _session_from_test_app()
    try:
        document = db.get(CaseDocument, document_id)
        document.processing_status = "processing"
        storage_key = document.storage_key
        db.commit()
    finally:
        db.close()
        generator.close()

    response = client.delete(f"/api/v1/cases/{case['id']}/documents/{document_id}")
    assert response.status_code == 409

    generator, db = _session_from_test_app()
    try:
        assert db.get(CaseDocument, document_id) is not None
        assert list(db.scalars(
            select(DocumentTextUnit).where(DocumentTextUnit.document_id == document_id)
        ).all())
        assert (settings.uploads_dir / storage_key).is_file()
    finally:
        db.close()
        generator.close()
