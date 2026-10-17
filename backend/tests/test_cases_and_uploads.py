from app.core.config import settings
from app.core import durable_worker
from app.db.models import CaseDocument
from app.services.document_extraction import (
    OCRResult,
    TesseractOCR,
    ExtractedTextUnit,
    _clean_repeated_ocr_edges,
    _normalize_extracted_text,
    extract_document,
)
from app.services.uploads import _matches_signature
from pathlib import Path
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from uuid import UUID

import fitz
from PIL import Image
import pytest
from sqlalchemy import select


def create_case(client) -> dict:
    response = client.post(
        "/api/v1/cases",
        json={
            "title": "Property dispute — Rao v. Mehta",
            "client_reference": "MATTER-001",
            "court": "Delhi High Court",
            "jurisdiction": "Delhi",
            "case_type": "Civil",
            "stage": "Pleadings",
        },
    )
    assert response.status_code == 201
    return response.json()


def make_image_bytes(format_name: str, color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 12), color).save(output, format=format_name)
    return output.getvalue()


def test_create_and_list_cases(client) -> None:
    case = create_case(client)

    detail = client.get(f"/api/v1/cases/{case['id']}")
    listing = client.get("/api/v1/cases")

    assert detail.status_code == 200
    assert detail.json()["title"] == "Property dispute — Rao v. Mehta"
    assert len(listing.json()) == 1
    assert listing.json()[0]["id"] == case["id"]


def test_case_number_and_hearing_date_are_saved_and_dashboard_status_is_returned(client) -> None:
    response = client.post("/api/v1/cases", json={
        "title": "Hearing schedule case", "case_number": "CS-18/2026", "next_hearing_date": "2026-11-12",
    })
    assert response.status_code == 201
    case = response.json()
    assert case["case_number"] == "CS-18/2026"
    assert case["next_hearing_date"] == "2026-11-12"
    listed = client.get("/api/v1/cases").json()[0]
    assert listed["analysis_status"] is None
    assert listed["attention_count"] == 0


def test_update_case_metadata_partially_and_clear_optional_fields(client) -> None:
    case = create_case(client)

    response = client.patch(
        f"/api/v1/cases/{case['id']}",
        json={"title": "  Updated matter title  ", "jurisdiction": None, "stage": " Evidence "},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Updated matter title"
    assert updated["jurisdiction"] is None
    assert updated["stage"] == "Evidence"
    assert updated["court"] == case["court"]
    assert updated["client_reference"] == case["client_reference"]


def test_update_case_rejects_empty_title_and_missing_cases(client) -> None:
    case = create_case(client)

    empty_title = client.patch(f"/api/v1/cases/{case['id']}", json={"title": "   "})
    no_fields = client.patch(f"/api/v1/cases/{case['id']}", json={})
    missing = client.patch(
        "/api/v1/cases/00000000-0000-0000-0000-000000000001", json={"stage": "Evidence"}
    )

    assert empty_title.status_code == 422
    assert no_fields.status_code == 422
    assert missing.status_code == 404


def test_uploads_supported_document_and_image_types(client, docx_bytes) -> None:
    case = create_case(client)
    png = make_image_bytes("PNG")
    jpeg = make_image_bytes("JPEG")
    tif = make_image_bytes("TIFF")
    tiff = make_image_bytes("TIFF", "green")
    files = [
        ("files", ("order.pdf", b"%PDF-1.7\ncase text", "application/pdf")),
        (
            "files",
            (
                "pleading.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ),
        ("files", ("scan.png", png, "image/png")),
        ("files", ("photo.jpg", jpeg, "image/jpeg")),
        ("files", ("scan.tif", tif, "image/tiff")),
        ("files", ("scan.tiff", tiff, "image/tiff")),
    ]

    response = client.post(f"/api/v1/cases/{case['id']}/documents", files=files)

    assert response.status_code == 201
    result = response.json()
    assert {item["file_extension"] for item in result["uploaded"]} == {
        ".pdf",
        ".docx",
        ".png",
        ".jpg",
        ".tif",
        ".tiff",
    }
    assert result["rejected"] == []
    assert len(client.get(f"/api/v1/cases/{case['id']}/documents").json()) == 6


def test_partial_upload_accepts_valid_and_reports_invalid_files(client) -> None:
    case = create_case(client)
    files = [
        ("files", ("order.pdf", b"%PDF-1.7\ncase text", "application/pdf")),
        ("files", ("not-really.pdf", b"plain text", "application/pdf")),
        ("files", ("program.exe", b"MZ", "application/octet-stream")),
    ]

    response = client.post(f"/api/v1/cases/{case['id']}/documents", files=files)

    assert response.status_code == 201
    body = response.json()
    assert len(body["uploaded"]) == 1
    assert len(body["rejected"]) == 2
    assert "contents do not match" in body["rejected"][0]["reason"]
    assert "Unsupported file type" in body["rejected"][1]["reason"]


def test_duplicate_file_is_not_stored_twice(client) -> None:
    case = create_case(client)
    file = ("files", ("order.pdf", b"%PDF-1.7\ncase text", "application/pdf"))

    response = client.post(
        f"/api/v1/cases/{case['id']}/documents", files=[file, file]
    )

    assert response.status_code == 201
    assert len(response.json()["uploaded"]) == 1
    assert response.json()["rejected"][0]["reason"] == "This file is already in the case."


def test_document_can_be_labeled_and_described(client) -> None:
    case = create_case(client)
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("order.pdf", b"%PDF-1.7 synthetic bytes", "application/pdf"))],
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["uploaded"][0]["id"]
    updated = client.patch(f"/api/v1/cases/{case['id']}/documents/{document_id}", json={
        "document_type": "order", "description": "Interim order on injunction application",
    })
    assert updated.status_code == 200
    assert updated.json()["document_type"] == "order"
    assert updated.json()["description"] == "Interim order on injunction application"


def test_document_can_be_replaced_without_creating_a_second_record(client) -> None:
    case = create_case(client)
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("old.pdf", b"%PDF-1.7 old synthetic file", "application/pdf"))],
    )
    document_id = uploaded.json()["uploaded"][0]["id"]
    replaced = client.put(
        f"/api/v1/cases/{case['id']}/documents/{document_id}/file",
        files={"file": ("new.pdf", b"%PDF-1.7 replacement synthetic file", "application/pdf")},
    )
    assert replaced.status_code == 200
    assert replaced.json()["id"] == document_id
    assert replaced.json()["original_filename"] == "new.pdf"
    assert replaced.json()["processing_status"] == "queued"
    documents = client.get(f"/api/v1/cases/{case['id']}/documents").json()
    assert len(documents) == 1


def test_upload_rejects_files_over_configured_limit(client, monkeypatch) -> None:
    case = create_case(client)
    monkeypatch.setattr(settings, "max_upload_size_bytes", 16)

    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("large.pdf", b"%PDF-1.7" + b"x" * 20, "application/pdf"))],
    )

    assert response.status_code == 400
    assert "configured per-file size limit" in response.json()["detail"]["rejected"][0]["reason"]


def test_upload_enforces_batch_and_per_case_quotas(client, monkeypatch) -> None:
    case = create_case(client)
    monkeypatch.setattr(settings, "max_upload_files_per_batch", 1)
    too_many = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[
            ("files", ("one.pdf", b"%PDF-1.7 one", "application/pdf")),
            ("files", ("two.pdf", b"%PDF-1.7 two", "application/pdf")),
        ],
    )
    assert too_many.status_code == 413

    monkeypatch.setattr(settings, "max_upload_files_per_batch", 10)
    monkeypatch.setattr(settings, "max_case_documents", 1)
    partial = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[
            ("files", ("one.pdf", b"%PDF-1.7 one", "application/pdf")),
            ("files", ("two.pdf", b"%PDF-1.7 two", "application/pdf")),
        ],
    )

    assert partial.status_code == 201
    assert len(partial.json()["uploaded"]) == 1
    assert "document-count limit" in partial.json()["rejected"][0]["reason"]


def test_image_upload_rejects_excessive_decoded_pixel_count(tmp_path, monkeypatch) -> None:
    from app.services import uploads

    monkeypatch.setattr(uploads, "MAX_IMAGE_PIXELS", 100)
    path = tmp_path / "large.png"
    path.write_bytes(make_image_bytes("PNG"))

    assert not _matches_signature(path, ".png")


def test_docx_upload_rejects_excessive_archive_compression_ratio(tmp_path) -> None:
    path = tmp_path / "bomb.docx"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "document")
        archive.writestr("word/embedded.bin", "A" * (2 * 1024 * 1024))

    assert not _matches_signature(path, ".docx")


def test_production_uploads_fail_closed_without_malware_scanner(client, monkeypatch) -> None:
    case = create_case(client)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "clamav_command", None)

    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("order.pdf", b"%PDF-1.7 safe test", "application/pdf"))],
    )

    assert response.status_code == 400
    assert "malware scanner is unavailable" in response.json()["detail"]["rejected"][0]["reason"]
    assert client.get(f"/api/v1/cases/{case['id']}/documents").json() == []


def test_clamav_scanner_rejects_infected_files(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from app.services import uploads
    from app.services.uploads import UploadRejected

    monkeypatch.setattr(settings, "clamav_command", "clamscan")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(uploads.subprocess, "run", fake_run)
    path = tmp_path / "infected.pdf"
    path.write_bytes(b"test")

    with pytest.raises(UploadRejected, match="flagged by the malware scanner"):
        uploads._scan_malware(path)
    assert calls[0][0][0] == "clamscan"
    assert calls[0][1]["shell"] is False


def test_deleting_case_removes_files_and_case_data(client, monkeypatch) -> None:
    from app.api import analysis, summaries
    from app.core.database import get_db
    from app.db.models import CaseAnalysisRun, CaseSummaryRun
    from app.main import app

    case = create_case(client)
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "The agreement was signed on 12 March 2024.")
    pdf_bytes = pdf.tobytes()
    pdf.close()
    upload = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("order.pdf", pdf_bytes, "application/pdf"))],
    )
    assert upload.status_code == 201
    monkeypatch.setattr(settings, "gemini_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(analysis, "process_case_analysis", lambda *args, **kwargs: None)
    monkeypatch.setattr(summaries, "process_case_summary", lambda *args, **kwargs: None)
    assert client.post(f"/api/v1/cases/{case['id']}/analysis").status_code == 202
    assert client.post(f"/api/v1/cases/{case['id']}/summary").status_code == 202
    database_generator = app.dependency_overrides[get_db]()
    database = next(database_generator)
    try:
        for model in (CaseAnalysisRun, CaseSummaryRun):
            run = database.scalar(select(model).where(model.case_id == UUID(case["id"])))
            assert run is not None
            run.status = "failed"  # The processors are mocked; no job remains active.
        database.commit()
    finally:
        database.close()
        database_generator.close()
    storage_file = next((settings.uploads_dir / case["id"]).glob("*.pdf"))
    assert storage_file.is_file()

    deletion = client.delete(f"/api/v1/cases/{case['id']}")

    assert deletion.status_code == 204, deletion.text
    assert not storage_file.exists()
    assert client.get(f"/api/v1/cases/{case['id']}").status_code == 404
    assert client.get(f"/api/v1/cases/{case['id']}/analysis/latest").status_code == 404
    assert client.get(f"/api/v1/cases/{case['id']}/summary/latest").status_code == 404


def test_upload_rejects_missing_case(client) -> None:
    response = client.post(
        "/api/v1/cases/00000000-0000-0000-0000-000000000001/documents",
        files=[("files", ("order.pdf", b"%PDF-1.7", "application/pdf"))],
    )

    assert response.status_code == 404


def test_docx_upload_is_extracted_with_paragraph_citations(client, docx_bytes) -> None:
    case = create_case(client)
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[(
            "files",
            (
                "affidavit.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )],
    )
    assert response.status_code == 201
    document = response.json()["uploaded"][0]

    listed = client.get(f"/api/v1/cases/{case['id']}/documents").json()[0]
    extracted = client.get(f"/api/v1/cases/{case['id']}/documents/{document['id']}/text")

    assert listed["processing_status"] == "processed"
    assert listed["text_unit_count"] == 2
    assert len(extracted.json()) == 2
    assert extracted.json()[0]["locator_label"] == "Paragraph 1"
    assert "12 March 2024" in extracted.json()[0]["text"]


def test_worker_recovers_interrupted_document_and_marks_unhandled_failure(client, docx_bytes) -> None:
    case = create_case(client)
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("interrupted.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert uploaded.status_code == 201
    from uuid import UUID
    document_id = UUID(uploaded.json()["uploaded"][0]["id"])

    with durable_worker.SessionLocal() as db:
        document = db.get(CaseDocument, document_id)
        assert document is not None
        document.processing_status = "processing"
        db.commit()

    durable_worker._recover_interrupted_work()
    with durable_worker.SessionLocal() as db:
        recovered = db.get(CaseDocument, document_id)
        assert recovered is not None
        assert recovered.processing_status == "queued"
        recovered.processing_status = "processing"
        db.commit()

    durable_worker._record_task_failure(("document", document_id, None))
    with durable_worker.SessionLocal() as db:
        failed = db.get(CaseDocument, document_id)
        assert failed is not None
        assert failed.processing_status == "failed"
        assert "Retry extraction" in (failed.extraction_error or "")


def test_deleting_document_removes_upload_and_extracted_text(client, docx_bytes) -> None:
    case = create_case(client)
    uploaded = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("temporary-affidavit.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert uploaded.status_code == 201
    document = uploaded.json()["uploaded"][0]
    stored_files = list((settings.uploads_dir / case["id"]).iterdir())
    assert len(stored_files) == 1
    stored_path = stored_files[0]
    assert stored_path.is_file()

    deleted = client.delete(f"/api/v1/cases/{case['id']}/documents/{document['id']}")

    assert deleted.status_code == 204
    assert not stored_path.exists()
    assert client.get(f"/api/v1/cases/{case['id']}/documents").json() == []
    assert client.get(f"/api/v1/cases/{case['id']}/documents/{document['id']}/text").status_code == 404


def test_pdf_text_is_stored_by_source_page(client) -> None:
    pdf = fitz.open()
    for number in (1, 2):
        page = pdf.new_page()
        page.insert_text((72, 72), f"The notice was served on 12 March 2024. Page {number}.")
    pdf_bytes = pdf.tobytes()
    pdf.close()
    case = create_case(client)
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        files=[("files", ("notice.pdf", pdf_bytes, "application/pdf"))],
    )
    assert response.status_code == 201
    document_id = response.json()["uploaded"][0]["id"]

    listed = client.get(f"/api/v1/cases/{case['id']}/documents").json()[0]
    extracted = client.get(f"/api/v1/cases/{case['id']}/documents/{document_id}/text").json()

    assert listed["processing_status"] == "processed"
    assert [unit["locator_label"] for unit in extracted] == ["Page 1", "Page 2"]
    assert "Page 2" in extracted[1]["text"]


def test_pdf_preprocessing_removes_repeated_marginalia_and_page_numbers(tmp_path) -> None:
    pdf = fitz.open()
    for page_number in range(1, 4):
        page = pdf.new_page()
        page.insert_text((72, 35), "COURT COPY - Rao v. Mehta")
        page.insert_text((72, 100), f"Material evidence records service on page {page_number}.")
        page.insert_text((72, 200), "COURT COPY - Rao v. Mehta")
        page.insert_text((72, 760), f"Page {page_number} of 3")
    source = tmp_path / "repeated-marginalia.pdf"
    pdf.save(source)
    pdf.close()

    result = extract_document(source, ".pdf", [])

    assert result.status == "processed"
    assert len(result.units) == 3
    assert all("Material evidence" in unit.text for unit in result.units)
    assert all("Page " not in unit.text for unit in result.units)
    assert all(unit.text.count("COURT COPY") == 1 for unit in result.units)


def test_pdf_preprocessing_handles_small_header_ocr_variations(tmp_path) -> None:
    pdf = fitz.open()
    for page_number, header in enumerate(("COURT COPY - Rao v. Mehta", "COURT COPV - Rao v. Mehta", "COURT COPY - Rao v. Mehta"), start=1):
        page = pdf.new_page()
        page.insert_text((72, 35), header)
        page.insert_text((72, 100), f"Distinct evidence on page {page_number}.")
    source = tmp_path / "variant-headers.pdf"
    pdf.save(source)
    pdf.close()

    result = extract_document(source, ".pdf", [])

    assert all("COURT COP" not in unit.text for unit in result.units)
    assert all("Distinct evidence" in unit.text for unit in result.units)


def test_ocr_preprocessing_removes_repeated_edges_but_keeps_page_content() -> None:
    units = [
        ExtractedTextUnit(1, 1, "Page 1", "COURT OF DELHI\nNotice served on 4 March.\nPage 1 of 2", TesseractOCR.name),
        ExtractedTextUnit(2, 2, "Page 2", "COURT OF DELHI\nAffidavit filed on 8 March.\nPage 2 of 2", TesseractOCR.name),
    ]

    cleaned = _clean_repeated_ocr_edges(units)

    assert [unit.text for unit in cleaned] == [
        "Notice served on 4 March.",
        "Affidavit filed on 8 March.",
    ]


def test_ocr_edge_cleanup_handles_small_recognition_variations() -> None:
    units = [
        ExtractedTextUnit(1, 1, "Page 1", "COURT OF DELHI DISTRICT\nNotice served on 4 March.", TesseractOCR.name),
        ExtractedTextUnit(2, 2, "Page 2", "COURT OF DELHl DISTRICT\nAffidavit filed on 8 March.", TesseractOCR.name),
    ]

    cleaned = _clean_repeated_ocr_edges(units)

    assert [unit.text for unit in cleaned] == ["Notice served on 4 March.", "Affidavit filed on 8 March."]


def test_low_ocr_confidence_marks_result_for_review(tmp_path, monkeypatch) -> None:
    pdf = fitz.open()
    pdf.new_page()
    source = tmp_path / "low-confidence.pdf"
    pdf.save(source)
    pdf.close()
    monkeypatch.setattr(settings, "ocr_review_confidence_threshold", 70)

    class LowConfidenceOCR:
        name = "test_ocr"

        def recognize(self, image):
            return OCRResult("Scanned evidence text", 42.0)

    result = extract_document(source, ".pdf", [LowConfidenceOCR()])

    assert result.status == "needs_review"
    assert "42%" in result.error
    assert result.units[0].ocr_confidence == 42


def test_docx_extracts_footnotes_comments_and_supported_embedded_pdf(tmp_path, docx_bytes) -> None:
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Embedded order states payment was received on 12 March 2024.")
    embedded_pdf = pdf.tobytes()
    pdf.close()
    docx_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    footnotes = f'''<w:footnotes xmlns:w="{docx_namespace}"><w:footnote w:id="2"><w:p><w:r><w:t>Footnote supporting the limitation date.</w:t></w:r></w:p></w:footnote></w:footnotes>'''.encode()
    comments = f'''<w:comments xmlns:w="{docx_namespace}"><w:comment w:id="1"><w:p><w:r><w:t>Comment records a disputed service date.</w:t></w:r></w:p></w:comment></w:comments>'''.encode()
    package_bytes = BytesIO()
    with ZipFile(BytesIO(docx_bytes)) as original, ZipFile(package_bytes, "w", ZIP_DEFLATED) as updated:
        for info in original.infolist():
            updated.writestr(info, original.read(info.filename))
        updated.writestr("word/footnotes.xml", footnotes)
        updated.writestr("word/comments.xml", comments)
        updated.writestr("word/embeddings/attached-order.pdf", embedded_pdf)
    source = tmp_path / "filing.docx"
    source.write_bytes(package_bytes.getvalue())

    result = extract_document(source, ".docx", [])

    assert result.status == "processed"
    assert any(unit.locator_label == "Footnote 2" and "limitation date" in unit.text for unit in result.units)
    assert any(unit.locator_label == "Comment 1" and "disputed service date" in unit.text for unit in result.units)
    assert any("Embedded order states payment" in unit.text and "Embedded 1" in unit.locator_label for unit in result.units)


def test_text_preprocessing_normalizes_unicode_and_whitespace() -> None:
    text = "  The\u00a0notice\twas served.\r\n\r\n\x00  Signed\u00ad copy.  "

    assert _normalize_extracted_text(text) == "The notice was served.\n\nSigned copy."


def test_pdf_ocr_provider_chain_falls_through_to_optional_cloud_adapter(tmp_path) -> None:
    pdf = fitz.open()
    pdf.new_page()
    source = tmp_path / "scan.pdf"
    pdf.save(source)
    pdf.close()

    class UnavailableLocalOCR:
        name = "tesseract_ocr"

        def recognize(self, image):
            raise RuntimeError("local engine not installed")

    class CloudFallback:
        name = "cloud_ocr_test_double"

        def recognize(self, image):
            return OCRResult("Scanned court filing text", 96.5)

    result = extract_document(source, ".pdf", [UnavailableLocalOCR(), CloudFallback()])

    assert result.status == "processed"
    assert result.units[0].text == "Scanned court filing text"
    assert result.units[0].extraction_method == "cloud_ocr_test_double"
    assert result.units[0].ocr_confidence == 96.5


def test_missing_local_ocr_marks_scan_for_review_with_setup_guidance(tmp_path) -> None:
    pdf = fitz.open()
    pdf.new_page()
    source = tmp_path / "scan.pdf"
    pdf.save(source)
    pdf.close()

    class MissingTesseract:
        name = "tesseract_ocr"

        def recognize(self, image):
            class TesseractNotFoundError(Exception):
                pass

            raise TesseractNotFoundError()

    result = extract_document(source, ".pdf", [MissingTesseract()])

    assert result.status == "needs_review"
    assert "Install Tesseract OCR" in result.error
    assert result.units[0].locator_label == "Page 1"


def test_multipage_tiff_keeps_each_page_location(tmp_path) -> None:
    class StubOCR:
        name = "stub_local_ocr"

        def __init__(self):
            self.page = 0

        def recognize(self, image):
            self.page += 1
            return OCRResult(f"Page {self.page} evidence", 91.0)

    first = Image.new("RGB", (30, 30), "white")
    second = Image.new("RGB", (30, 30), "white")
    source = tmp_path / "bundle.tiff"
    first.save(source, save_all=True, append_images=[second])

    result = extract_document(Path(source), ".tiff", [StubOCR()])

    assert [unit.locator_label for unit in result.units] == ["Page 1", "Page 2"]
    assert result.units[1].text == "Page 2 evidence"
