from io import BytesIO
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from docx import Document

from app.core.config import settings
from app.services.gemini_analysis import GeminiCaseAnalyzer
from app.services.legal_research import IndiaCodeProvider
from app.api.chat import _answer_from_cited_statements, _citations_cover_answer, _fuse_context_units


def make_docx(text: str) -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def test_answer_keeps_only_source_validated_answer_statements():
    answer = "The affidavit states 12 March. The filing states 13 March. This proves fraud."
    citations = [
        {"statement": "The affidavit states 12 March."},
        {"statement": "The filing states 13 March."},
    ]
    assert _answer_from_cited_statements(answer, citations) == (
        "The affidavit states 12 March.\nThe filing states 13 March."
    )
    assert _citations_cover_answer("The affidavit states 12 March.", citations)
    assert not _citations_cover_answer(answer, citations)


def test_hybrid_context_fusion_combines_rankings_and_spreads_documents():
    def passage(document_id, unit_number):
        return SimpleNamespace(
            id=uuid4(),
            document_id=document_id,
            unit_number=unit_number,
            document=SimpleNamespace(uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )

    first_doc, second_doc = uuid4(), uuid4()
    lexical_best = passage(first_doc, 1)
    lexical_second = passage(first_doc, 2)
    graph_best = passage(second_doc, 1)
    graph_shared = passage(first_doc, 3)

    fused = _fuse_context_units(
        [lexical_best, lexical_second], [graph_best, graph_shared], [], [], limit=3
    )

    assert len(fused) == 3
    assert fused[0] is lexical_best or fused[0] is graph_best
    assert {item.document_id for item in fused[:2]} == {first_doc, second_doc}
    assert len({item.id for item in fused}) == 3


def create_case(client, title="Chat case"):
    response = client.post("/api/v1/cases", json={"title": title})
    assert response.status_code == 201
    return response.json()


def upload_docx(client, case_id, filename, text):
    response = client.post(
        f"/api/v1/cases/{case_id}/documents",
        files=[("files", (filename, make_docx(text), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
    )
    assert response.status_code == 201
    return response.json()["uploaded"][0]


def test_case_chat_uses_all_case_documents_and_only_india_code(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "gemini_model", "test-model")
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was delivered on 12 March 2024 by registered post.")
    upload_docx(client, case["id"], "filing.docx", "The court filing states that the notice was delivered on 13 March 2024.")
    conversation = client.post(f"/api/v1/cases/{case['id']}/chat/conversations", json={}).json()
    provider_calls = []

    async def india_code_search(self, query, limit, page=0):
        provider_calls.append((query, limit))
        return [{"provider": "india_code", "title": "Evidence Act", "url": "https://indiacode.ecourtsindia.com/act/1", "snippet": "Admissibility of evidence", "citation": "Section 3"}]

    monkeypatch.setattr(IndiaCodeProvider, "search", india_code_search)
    captured = {}
    generation_count = 0

    def fake_generate(self, prompt, schema):
        nonlocal generation_count
        generation_count += 1
        captured["prompt"] = prompt
        sources = json.loads(prompt.split("CASE DOCUMENT PASSAGES (JSON):\n", 1)[1].split("\n\nVERIFIED LATEST CASE SUMMARY", 1)[0])
        return schema(
            answer=(
                "The two files give different delivery dates. Please verify the original records."
                if generation_count == 1 else "The two files give different delivery dates."
            ),
            document_citations=[
                {
                    "source_unit_id": item["source_unit_id"],
                    "quote": item["text"][:45],
                    "statement": "The two files give different delivery dates.",
                }
                for item in sources
            ],
            authority_citations=[{
                "result_index": 0,
                "quote": "Admissibility of evidence",
                "statement": "The two files give different delivery dates.",
            }],
            follow_up_questions=["Do you have the postal receipt?"]
        )

    monkeypatch.setattr(GeminiCaseAnalyzer, "_generate", fake_generate)
    response = client.post(
        f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}/messages",
        json={"content": "Compare the notice delivery dates for Asha Rao on 12 March 2024 under Section 9 CPC", "include_india_code": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assistant = body["messages"][-1]
    assert "affidavit.docx" in captured["prompt"]
    assert "filing.docx" in captured["prompt"]
    assert len([citation for citation in assistant["citations"] if citation["kind"] == "document"]) == 2
    assert any(citation["kind"] == "india_code" for citation in assistant["citations"])
    assert assistant["content"] == "The two files give different delivery dates."
    assert generation_count == 2
    assert all(citation["statement"] in assistant["content"] for citation in assistant["citations"])
    assert all(
        citation["source_start_char"] is not None
        and citation["source_end_char"] - citation["source_start_char"] == len(citation["quote"])
        for citation in assistant["citations"] if citation["kind"] == "document"
    )
    assert assistant["follow_up_questions"] == ["Do you have the postal receipt?"]
    assert provider_calls == [("Section 9 CPC", 4)]
    assert "Asha Rao" not in provider_calls[0][0] and "12 March 2024" not in provider_calls[0][0]
    assert len(body["messages"]) == 2


def test_case_chat_drops_quotes_not_found_in_source_and_handles_india_code_failure(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    case = create_case(client, "Quote validation case")
    upload_docx(client, case["id"], "record.docx", "The hearing was listed on 8 April 2025.")
    conversation = client.post(f"/api/v1/cases/{case['id']}/chat/conversations", json={}).json()

    async def failed_search(self, query, limit, page=0):
        raise RuntimeError("provider offline")

    monkeypatch.setattr(IndiaCodeProvider, "search", failed_search)

    def fake_generate(self, prompt, schema):
        match = re.search(r'"source_unit_id": "([^"]+)"', prompt)
        return schema(
            answer="The hearing is listed on 8 April 2025.",
            document_citations=[
                {"source_unit_id": match.group(1), "quote": "Invented quote that is not in the file"},
                {
                    "source_unit_id": match.group(1),
                    "quote": "The hearing was listed on 8 April 2025.",
                    "statement": "The hearing is listed on 8 April 2025.",
                },
            ],
        )

    monkeypatch.setattr(GeminiCaseAnalyzer, "_generate", fake_generate)
    response = client.post(
        f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}/messages",
        json={"content": "What legal rule applies to the hearing date under Section 9 CPC?", "include_india_code": True},
    )
    assert response.status_code == 200
    assistant = response.json()["messages"][-1]
    assert len(assistant["citations"]) == 1
    assert "India Code could not be reached" in assistant["content"]
    assert "could not verify a relevant legal authority" in assistant["content"]


def test_case_chat_conversation_cannot_be_read_or_used_from_another_case(client):
    first = create_case(client, "First matter")
    second = create_case(client, "Second matter")
    conversation = client.post(f"/api/v1/cases/{first['id']}/chat/conversations", json={}).json()
    assert client.get(f"/api/v1/cases/{second['id']}/chat/conversations/{conversation['id']}").status_code == 404
    assert client.post(
        f"/api/v1/cases/{second['id']}/chat/conversations/{conversation['id']}/messages",
        json={"content": "Read the other case"},
    ).status_code == 404


def test_case_chat_conversation_can_be_renamed_and_deleted(client):
    case = create_case(client, "Conversation lifecycle")
    conversation = client.post(f"/api/v1/cases/{case['id']}/chat/conversations", json={}).json()
    renamed = client.patch(
        f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}",
        json={"title": "  Hearing   evidence  "},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Hearing evidence"
    deleted = client.delete(f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}").status_code == 404


def test_case_chat_rate_limits_turns_per_case(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "chat_messages_per_minute", 1)
    case = create_case(client, "Rate limit case")
    upload_docx(client, case["id"], "record.docx", "The hearing was listed on 8 April 2025.")
    conversation = client.post(f"/api/v1/cases/{case['id']}/chat/conversations", json={}).json()
    monkeypatch.setattr(GeminiCaseAnalyzer, "_generate", lambda self, prompt, schema: schema(answer="The file lists a hearing date."))
    path = f"/api/v1/cases/{case['id']}/chat/conversations/{conversation['id']}/messages"
    first = client.post(path, json={"content": "When is the hearing?", "include_india_code": False})
    second = client.post(path, json={"content": "When is the hearing?", "include_india_code": False})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"
