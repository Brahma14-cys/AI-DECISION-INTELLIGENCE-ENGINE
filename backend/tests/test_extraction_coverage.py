from types import SimpleNamespace

from app.core.config import settings
from app.db.models import CaseDocument
from app.services import document_processing
from app.services.document_extraction import ExtractedTextUnit, ExtractionResult
from app.api import analysis, summaries


def test_page_coverage_counts_each_page_in_exactly_one_bucket() -> None:
    document = SimpleNamespace(text_units=[
        SimpleNamespace(page_number=1, text="Readable text"),
        SimpleNamespace(page_number=1, text=""),
        SimpleNamespace(page_number=2, text=""),
    ])

    pages_with_text = CaseDocument.pages_with_text_count.fget(document)
    pages_without_text = CaseDocument.pages_without_text_count.fget(document)

    assert pages_with_text == 1
    assert pages_without_text == 1
    assert pages_with_text + pages_without_text == 2


def _upload_partial_pdf(client, case_id: str, monkeypatch) -> dict:
    monkeypatch.setattr(
        document_processing,
        "extract_document",
        lambda *_args, **_kwargs: ExtractionResult(
            units=[
                ExtractedTextUnit(1, 1, "Page 1", "The notice was served on 12 March 2024.", "embedded_text"),
                ExtractedTextUnit(2, 2, "Page 2", "", "tesseract_ocr", 55.0),
            ],
            status="needs_review",
            error="Page 2 has low OCR confidence; verify the scan.",
        ),
    )
    response = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files=[("files", ("partial.pdf", b"%PDF-1.7\nsynthetic", "application/pdf"))],
    )
    assert response.status_code == 201
    return response.json()["uploaded"][0]


def test_document_list_reports_page_and_ocr_coverage(client, monkeypatch) -> None:
    case = client.post("/api/v1/cases", json={"title": "Coverage test"}).json()
    _upload_partial_pdf(client, case["id"], monkeypatch)

    response = client.get(f"/api/v1/cases/{case['id']}/documents")

    assert response.status_code == 200
    document = response.json()[0]
    assert document["processing_status"] == "needs_review"
    assert document["text_unit_count"] == 2
    assert document["readable_location_count"] == 1
    assert document["unreadable_location_count"] == 1
    assert document["page_count"] == 2
    assert document["pages_with_text_count"] == 1
    assert document["pages_without_text_count"] == 1
    assert document["review_location_count"] == 1


def test_analysis_and_summary_require_incomplete_source_acknowledgement(client, monkeypatch) -> None:
    case = client.post("/api/v1/cases", json={"title": "Incomplete source gate"}).json()
    _upload_partial_pdf(client, case["id"], monkeypatch)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(analysis, "process_case_analysis", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(summaries, "process_case_summary", lambda *_args, **_kwargs: None)

    analysis_blocked = client.post(f"/api/v1/cases/{case['id']}/analysis")
    summary_blocked = client.post(f"/api/v1/cases/{case['id']}/summary")
    assert analysis_blocked.status_code == 409
    assert analysis_blocked.json()["detail"]["code"] == "incomplete_sources_acknowledgement_required"
    assert summary_blocked.status_code == 409
    assert summary_blocked.json()["detail"]["code"] == "incomplete_sources_acknowledgement_required"

    analysis_accepted = client.post(
        f"/api/v1/cases/{case['id']}/analysis",
        json={"acknowledge_incomplete_sources": True},
    )
    summary_accepted = client.post(
        f"/api/v1/cases/{case['id']}/summary",
        json={"acknowledge_incomplete_sources": True},
    )
    assert analysis_accepted.status_code == 202
    assert analysis_accepted.json()["incomplete_sources_acknowledged"] is True
    assert summary_accepted.status_code == 202
    assert summary_accepted.json()["incomplete_sources_acknowledged"] is True
