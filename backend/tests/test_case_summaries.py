from io import BytesIO

from docx import Document

from app.core.config import settings
from app.services import summary_processing
from app.services.gemini_analysis import (
    CaseSummaryDraft,
    SummaryCitation,
    SummaryPoint,
    SummarySection,
)


def make_docx(text: str) -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def create_case(client) -> dict:
    response = client.post("/api/v1/cases", json={"title": "Summary integration test"})
    assert response.status_code == 201
    return response.json()


def upload_docx(client, case_id: str, filename: str, text: str) -> dict:
    response = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files=[
            (
                "files",
                (
                    filename,
                    make_docx(text),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            )
        ],
    )
    assert response.status_code == 201
    return response.json()["uploaded"][0]


class StubGeminiSummarizer:
    def __init__(self):
        self.summarize_calls = 0
        self.synthesis_calls = 0

    def summarize_sources(self, sources) -> CaseSummaryDraft:
        self.summarize_calls += 1
        citations = [
            SummaryCitation(source_unit_id=source.source_unit_id, evidence_quote=source.text[:80].strip())
            for source in sources
            if len(source.text.strip()) >= 3
        ][:5]
        point = SummaryPoint(text="The source passages describe the notice and its service date.", citations=citations)
        return CaseSummaryDraft(
            narrative=[point],
            structured_sections=[
                SummarySection(
                    section_key="material_facts_and_timeline",
                    title="Material facts and timeline",
                    points=[point],
                )
            ],
        )

    def synthesize_summary(self, drafts) -> CaseSummaryDraft:
        self.synthesis_calls += 1
        citations = []
        seen = set()
        for draft in drafts:
            for point in draft.narrative:
                for citation in point.citations:
                    key = (citation.source_unit_id, citation.evidence_quote)
                    if key not in seen:
                        citations.append(citation)
                        seen.add(key)
        point = SummaryPoint(
            text="Integrated: the source passages describe the notice and its service date.",
            citations=citations[:5],
        )
        return CaseSummaryDraft(
            narrative=[point],
            structured_sections=[
                SummarySection(
                    section_key="material_facts_and_timeline",
                    title="Material facts and timeline",
                    points=[point],
                )
            ],
        )


def configure_paid_gemini(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "gemini_model", "gemini-3.8-flash")


def test_case_summary_integrates_multiple_documents_in_both_formats(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    fake = StubGeminiSummarizer()
    monkeypatch.setattr(summary_processing, "GeminiCaseAnalyzer", lambda: fake)
    case = create_case(client)
    upload_docx(
        client,
        case["id"],
        "affidavit.docx",
        "The notice was served on 12 March 2024. " + ("Affidavit detail. " * 900),
    )
    upload_docx(
        client,
        case["id"],
        "court-filing.docx",
        "The notice was served on 13 March 2024. " + ("Court filing detail. " * 900),
    )

    started = client.post(f"/api/v1/cases/{case['id']}/summary")
    result = client.get(f"/api/v1/cases/{case['id']}/summary/latest")

    assert started.status_code == 202
    assert result.status_code == 200
    body = result.json()
    assert body["run"]["status"] == "completed"
    assert body["run"]["document_count"] == 2
    assert body["narrative_summary"]
    assert body["structured_summary"]
    assert fake.summarize_calls == 2
    assert fake.synthesis_calls == 1
    source_names = {
        citation["source_filename"]
        for point in body["narrative_summary"]
        for citation in point["citations"]
    }
    assert source_names == {"affidavit.docx", "court-filing.docx"}
    assert all(citation["source_locator"] == "Paragraph 1" for point in body["narrative_summary"] for citation in point["citations"])


def test_case_summary_rejects_unverifiable_quotes(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)

    class HallucinatingSummarizer(StubGeminiSummarizer):
        def summarize_sources(self, sources) -> CaseSummaryDraft:
            return CaseSummaryDraft(
                narrative=[
                    SummaryPoint(
                        text="A claim with a fabricated quote.",
                        citations=[
                            SummaryCitation(
                                source_unit_id=sources[0].source_unit_id,
                                evidence_quote="This quote is not in the source passage.",
                            )
                        ],
                    )
                ],
                structured_sections=[],
            )

    monkeypatch.setattr(summary_processing, "GeminiCaseAnalyzer", HallucinatingSummarizer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")

    started = client.post(f"/api/v1/cases/{case['id']}/summary")
    result = client.get(f"/api/v1/cases/{case['id']}/summary/latest")

    assert started.status_code == 202
    assert result.status_code == 200
    assert result.json()["run"]["status"] == "failed"
    assert result.json()["narrative_summary"] == []
