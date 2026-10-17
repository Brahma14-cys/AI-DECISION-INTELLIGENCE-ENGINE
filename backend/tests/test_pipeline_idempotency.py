from uuid import UUID

from sqlalchemy import func, select

from app.api import analysis, summaries
from app.core.config import settings
from app.core.database import get_db
from app.db.models import CaseAnalysisRun, CaseDocument, CaseSummaryRun
from app.main import app


def test_active_analysis_and_summary_requests_do_not_enqueue_duplicates(client, docx_bytes, monkeypatch):
    case = client.post("/api/v1/cases", json={"title": "Idempotent pipeline start"}).json()
    upload = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert upload.status_code == 201
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(analysis, "gemini_is_ready", lambda: True)
    monkeypatch.setattr(summaries, "gemini_is_ready", lambda: True)

    first_analysis = client.post(f"/api/v1/cases/{case['id']}/analysis")
    second_analysis = client.post(f"/api/v1/cases/{case['id']}/analysis")
    first_summary = client.post(f"/api/v1/cases/{case['id']}/summary")
    second_summary = client.post(f"/api/v1/cases/{case['id']}/summary")

    assert first_analysis.status_code == 202
    assert second_analysis.status_code == 409
    assert first_summary.status_code == 202
    assert second_summary.status_code == 409

    database_generator = app.dependency_overrides[get_db]()
    database = next(database_generator)
    try:
        case_id = UUID(case["id"])
        assert database.scalar(select(func.count(CaseAnalysisRun.id)).where(CaseAnalysisRun.case_id == case_id)) == 1
        assert database.scalar(select(func.count(CaseSummaryRun.id)).where(CaseSummaryRun.case_id == case_id)) == 1
    finally:
        database.close()
        database_generator.close()


def test_document_mutations_wait_until_case_jobs_finish(client, docx_bytes):
    case = client.post("/api/v1/cases", json={"title": "Stable processing input"}).json()
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("record.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    ).json()["uploaded"][0]
    case_id = UUID(case["id"])
    document_id = UUID(uploaded["id"])
    database_generator = app.dependency_overrides[get_db]()
    database = next(database_generator)
    try:
        database.add(CaseSummaryRun(
            case_id=case_id, status="queued", provider="google_gemini", model="test-model",
            document_count=1, text_unit_count=1,
        ))
        database.commit()
        document = database.get(CaseDocument, document_id)
        document.processing_status = "failed"
        database.commit()
    finally:
        database.close()
        database_generator.close()

    added = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files=[("files", ("another.pdf", b"%PDF-1.7 synthetic", "application/pdf"))],
    )
    deleted = client.delete(f"/api/v1/cases/{case_id}/documents/{document_id}")
    replaced = client.put(
        f"/api/v1/cases/{case_id}/documents/{document_id}/file",
        files={"file": ("replacement.pdf", b"%PDF-1.7 replacement", "application/pdf")},
    )
    retried = client.post(f"/api/v1/cases/{case_id}/documents/{document_id}/extract")

    assert [added.status_code, deleted.status_code, replaced.status_code, retried.status_code] == [409, 409, 409, 409]
    assert len(client.get(f"/api/v1/cases/{case_id}/documents").json()) == 1
