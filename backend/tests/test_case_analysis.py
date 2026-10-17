from io import BytesIO
import json
from uuid import uuid4

from docx import Document
from google import genai

from app.core.config import settings
from app.db.models import CaseAnalysisFact, DocumentTextUnit
from app.services import case_analysis_processing
from app.services.case_semantic_retrieval import semantic_candidate_pairs
from app.services.case_analysis_processing import (
    _batch_sources,
    _fact_pair_candidates,
    _find_source_span,
    _find_source_span_range,
    _manual_claim_candidates,
    _persist_extraction_items,
    _sentence_spans,
    _split_source,
)
from app.services.gemini_analysis import (
    ClaimAssessment,
    ClaimAssessmentBatch,
    ExtractedEntity,
    ExtractedFact,
    ExtractedFactBatch,
    ExtractedLegalReference,
    ExtractedSentence,
    FactForComparison,
    GeminiCaseAnalyzer,
    RelatedFactBatch,
    RelatedFactPair,
    SourceText,
    StructuredExtractionItem,
)


def make_docx(text: str) -> bytes:
    output = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def test_sentence_segmentation_preserves_abbreviations_and_source_offsets() -> None:
    text = "Dr. Rao filed Case No. 12 on 3.5 acres. Notice was served later!"
    spans = _sentence_spans(text)

    assert [text[start:end] for start, end in spans] == [
        "Dr. Rao filed Case No. 12 on 3.5 acres.",
        "Notice was served later!",
    ]
    source = SourceText(
        source_unit_id=uuid4(),
        document_name="sample.pdf",
        locator="Page 2",
        text="  " + text,
        source_start_char=10,
    )
    segments = _split_source(source)
    assert segments[0].text == "Dr. Rao filed Case No. 12 on 3.5 acres."
    assert segments[0].source_start_char == 12
    assert segments[1].source_start_char == 12 + len(segments[0].text) + 1


def test_long_sentence_is_bounded_without_losing_text_or_splitting_words() -> None:
    text = ("A legal assertion with enough words; " * 500).strip()
    source = SourceText(
        source_unit_id=uuid4(), document_name="long.pdf", locator="Page 1", text=text
    )
    segments = _split_source(source)

    assert len(segments) > 1
    assert all(len(segment.text) <= 8_000 for segment in segments)
    assert all(
        source.text[segment.source_start_char:segment.source_start_char + len(segment.text)] == segment.text
        for segment in segments
    )
    covered = " ".join(segment.text for segment in segments)
    assert "".join(covered.split()) == "".join(text.split())
    assert all(not segment.text.endswith(" ") and not segment.text.startswith(" ") for segment in segments)


def test_extremely_long_unbroken_sentence_uses_documented_hard_split() -> None:
    text = "क" * 16_010
    source = SourceText(source_unit_id=uuid4(), document_name="scan.txt", locator="Page 1", text=text)

    segments = _split_source(source)

    assert [len(segment.text) for segment in segments] == [8_000, 8_000, 10]
    assert "".join(segment.text for segment in segments) == text
    assert [segment.source_start_char for segment in segments] == [0, 8_000, 16_000]


def test_source_span_finds_repeated_and_unicode_casefolded_mentions() -> None:
    source = "Rao filed the claim. Rao filed the claim. Straße"

    first = _find_source_span(source, "Rao")
    second = _find_source_span(source, "Rao", first + len("Rao"))

    assert first == 0
    assert second == source.index("Rao", first + 1)
    assert _find_source_span(source, "STRASSE") == source.index("Straße")
    sharp_s_start = source.index("Straße")
    assert _find_source_span_range(source, "STRASSE") == (sharp_s_start, sharp_s_start + len("Straße"))
    assert _find_source_span("ß", "s") is None


def test_provider_batches_respect_response_sentence_limit() -> None:
    sources = [
        SourceText(source_unit_id=uuid4(), document_name="case.pdf", locator=f"Page {i}", text="Fact.")
        for i in range(250)
    ]

    batches = _batch_sources(sources)

    assert [len(batch) for batch in batches] == [50, 50, 50, 50, 50]


def test_extracted_fact_batch_discards_short_sentence_markers() -> None:
    source_id = str(uuid4())
    result = ExtractedFactBatch.model_validate({
        "facts": [],
        "sentences": [
            {"source_unit_id": source_id, "classification": "irrelevant", "sentence": "1.", "confidence": 0.5},
            {"source_unit_id": source_id, "classification": "fact", "sentence": "Notice was served.", "confidence": 0.8},
        ],
        "entities": [],
        "legal_references": [],
    })

    assert [item.sentence for item in result.sentences] == ["Notice was served."]


def test_gemini_extraction_splits_batches_after_invalid_structured_output(monkeypatch) -> None:
    analyzer = GeminiCaseAnalyzer.__new__(GeminiCaseAnalyzer)
    attempted_sizes = []

    def generate(prompt, schema):
        payload = json.loads(prompt.split("SOURCE PASSAGES (JSON):\n", 1)[1])
        attempted_sizes.append(len(payload))
        if len(payload) > 2:
            schema.model_validate_json("{")
        return schema(
            facts=[],
            sentences=[
                ExtractedSentence(
                    source_unit_id=item["source_unit_id"],
                    classification="fact",
                    sentence=item["text"],
                    confidence=0.8,
                )
                for item in payload
            ],
            entities=[],
            legal_references=[],
        )

    monkeypatch.setattr(analyzer, "_generate", generate)
    sources = [
        SourceText(
            source_unit_id=uuid4(),
            document_name="judgment.pdf",
            locator=f"Page {index + 1}",
            text=f"Source statement {index + 1}.",
        )
        for index in range(5)
    ]

    result = analyzer.extract_facts(sources)

    assert attempted_sizes == [5, 2, 3, 1, 2]
    assert {item.source_unit_id for item in result.sentences} == {source.source_unit_id for source in sources}


def test_persisted_duplicate_mentions_keep_independent_offsets() -> None:
    source_id = uuid4()
    source_text = "Section 138 applies. Section 138 is also mentioned later."
    item = StructuredExtractionItem(
        source_unit_id=source_id,
        item_kind="legal_reference",
        category="section_or_rule",
        text="Section 138",
        evidence_quote="Section 138",
        confidence=1,
        extractor="regex",
    )

    class Collector:
        def __init__(self):
            self.items = []

        def add(self, value):
            self.items.append(value)

    db = Collector()
    _persist_extraction_items(
        db,
        uuid4(),
        [item, item.model_copy(deep=True)],
        {source_id: uuid4()},
        {source_id: source_text},
        {source_id: 0},
        set(),
        {},
    )

    assert [value.source_start_char for value in db.items] == [0, source_text.index("Section 138", 1)]


def test_fact_confidence_is_adjusted_for_ocr_quality_without_overwriting_model_estimate() -> None:
    source = DocumentTextUnit(
        document_id=uuid4(),
        unit_number=1,
        page_number=1,
        locator_label="Page 1",
        text="Notice served on 12 March.",
        character_count=27,
        extraction_method="tesseract_ocr",
        ocr_confidence=50,
    )
    fact = CaseAnalysisFact(confidence=0.9, source_unit=source)

    assert fact.confidence == 0.9
    assert fact.effective_confidence == 0.45
    assert fact.source_ocr_confidence == 50
    assert fact.ocr_needs_review


def create_case(client) -> dict:
    response = client.post("/api/v1/cases", json={"title": "Notice service date dispute"})
    assert response.status_code == 201
    return response.json()


def test_analysis_change_summary_is_empty_before_first_completed_run(client) -> None:
    case = create_case(client)
    response = client.get(f"/api/v1/cases/{case['id']}/analysis/changes")
    assert response.status_code == 200
    assert response.json() == {
        "latest_run_at": None, "previous_run_at": None, "new_facts": [],
        "new_findings": [], "resolved_findings": [], "documents_since_previous_run": [],
    }


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


class StubGeminiAnalyzer:
    def extract_facts(self, sources) -> ExtractedFactBatch:
        facts = []
        sentences = []
        entities = []
        legal_references = []
        for source in sources:
            sentences.append(
                ExtractedSentence(
                    source_unit_id=source.source_unit_id,
                    classification="fact",
                    sentence=source.text,
                    confidence=0.91,
                )
            )
            if "notice" in source.text.casefold():
                entities.append(
                    ExtractedEntity(
                        source_unit_id=source.source_unit_id,
                        entity_text="notice",
                        canonical_name="notice",
                        entity_type="other",
                        legal_role=None,
                        evidence_quote=source.text,
                        confidence=0.82,
                    )
                )
            if "Section 138" in source.text:
                legal_references.append(
                    ExtractedLegalReference(
                        source_unit_id=source.source_unit_id,
                        reference_text="Section 138",
                        normalized_reference="Section 138",
                        reference_type="section",
                        evidence_quote=source.text,
                        confidence=0.96,
                    )
                )
            if "12 March 2024" in source.text or "13 March 2024" in source.text:
                date = "12 March 2024" if "12 March 2024" in source.text else "13 March 2024"
                facts.append(
                    ExtractedFact(
                        source_unit_id=source.source_unit_id,
                        fact_type="date",
                        topic_key="notice_service_date",
                        statement=f"The notice was served on {date}.",
                        evidence_quote=f"The notice was served on {date}.",
                        normalized_value=date,
                        confidence=0.94,
                    )
                )
        return ExtractedFactBatch(
            facts=facts,
            sentences=sentences,
            entities=entities,
            legal_references=legal_references,
        )

    def compare_facts(self, facts, candidate_pairs=None) -> RelatedFactBatch:
        if len(facts) < 2:
            return RelatedFactBatch(findings=[])
        if facts[0].normalized_value == facts[1].normalized_value:
            return RelatedFactBatch(
                findings=[
                    RelatedFactPair(
                        left_fact_id=facts[0].fact_id,
                        right_fact_id=facts[1].fact_id,
                        finding_type="relation",
                        relation_label="repeats",
                        explanation="Both documents state the same service date.",
                        confidence=0.93,
                    )
                ]
            )
        return RelatedFactBatch(
            findings=[
                RelatedFactPair(
                    left_fact_id=facts[0].fact_id,
                    right_fact_id=facts[1].fact_id,
                    finding_type="contradiction",
                    relation_label=None,
                    explanation="The documents state different dates for the same service event.",
                    confidence=0.91,
                )
            ]
        )

    def assess_claims(self, claims) -> ClaimAssessmentBatch:
        return ClaimAssessmentBatch(
            assessments=[
                ClaimAssessment(
                    claim_id=claim.claim_id,
                    support_status="partially_supported",
                    explanation="The other document contains a related account that supports only part of this claim.",
                    is_overstated=claim.claim_text.startswith("The notice was served"),
                    overstatement_reason="The source states a date, but does not establish every implication in the broader wording.",
                    evidence_fact_ids=[claim.evidence_facts[0].fact_id] if claim.evidence_facts else [],
                )
                for claim in claims
            ]
        )


def make_fact(document_id, *, topic, statement, value=None, fact_type="event", confidence=0.9):
    source = DocumentTextUnit(
        id=uuid4(),
        document_id=document_id,
        unit_number=1,
        page_number=1,
        locator_label="Page 1",
        text=statement,
        character_count=len(statement),
        extraction_method="embedded_text",
    )
    return CaseAnalysisFact(
        id=uuid4(),
        source_unit=source,
        fact_type=fact_type,
        topic_key=topic,
        statement=statement,
        evidence_quote=statement,
        normalized_value=value,
        confidence=confidence,
    )


def test_pair_retrieval_finds_cross_document_facts_with_different_topic_keys() -> None:
    affidavit = make_fact(
        uuid4(),
        topic="notice_dispatch_date",
        statement="The statutory notice was dispatched by registered post on 12 March 2024.",
        value="2024-03-12",
        fact_type="date",
    )
    filing = make_fact(
        uuid4(),
        topic="postal_delivery_event",
        statement="The registered post notice dispatch occurred on 13 March 2024.",
        value="2024-03-13",
        fact_type="date",
    )
    unrelated = make_fact(
        uuid4(),
        topic="payment_amount",
        statement="The respondent deposited a payment of INR 50,000.",
        value="INR 50000",
        fact_type="amount",
    )

    pairs = _fact_pair_candidates([affidavit, filing, unrelated])
    pair_ids = {frozenset((left.id, right.id)) for left, right in pairs}

    assert frozenset((affidavit.id, filing.id)) in pair_ids
    assert all(unrelated.id not in pair for pair in pair_ids)


def test_pair_retrieval_uses_normalized_value_and_never_compares_within_one_document() -> None:
    first = make_fact(
        uuid4(), topic="notice_date", statement="Notice was dispatched on 12 March 2024.",
        value="12 March 2024", fact_type="date",
    )
    second = make_fact(
        uuid4(), topic="dispatch_recorded", statement="The postal event took place on the twelfth day.",
        value="12-March-2024", fact_type="date",
    )
    same_document = make_fact(
        first.source_unit.document_id, topic="notice_date", statement="Notice date: 12/03/2024.",
        value="12 March 2024", fact_type="date",
    )

    pairs = _fact_pair_candidates([first, second, same_document])
    pair_ids = {frozenset((left.id, right.id)) for left, right in pairs}

    assert frozenset((first.id, second.id)) in pair_ids
    assert frozenset((first.id, same_document.id)) not in pair_ids


def test_claim_candidates_rank_relevant_source_facts_ahead_of_generic_overlap() -> None:
    relevant = make_fact(
        uuid4(), topic="notice_service", statement="Registered notice served upon Rao on 12 March 2024.",
    )
    generic = make_fact(
        uuid4(), topic="court_procedure", statement="The court recorded the matter in the case file.",
    )

    candidates = _manual_claim_candidates(
        "Rao received registered notice on 12 March 2024", [generic, relevant]
    )

    assert candidates[0] is relevant


def test_semantic_retrieval_finds_paraphrased_cross_document_facts_without_storing_vectors() -> None:
    affidavit = make_fact(
        uuid4(), topic="notice_service", statement="The statutory notice was delivered to the respondent.",
        fact_type="event",
    )
    filing = make_fact(
        uuid4(), topic="postal_dispatch", statement="Postal records show receipt of the legal demand.",
        fact_type="event",
    )
    same_document = make_fact(
        affidavit.source_unit.document_id, topic="notice_service", statement="The notice was sent by post.",
        fact_type="event",
    )

    pairs = semantic_candidate_pairs(
        [affidavit, filing, same_document],
        [[1.0, 0.0], [0.98, 0.2], [0.96, 0.28]],
        similarity_threshold=0.9,
    )
    pair_ids = {frozenset((left.id, right.id)) for left, right in pairs}

    assert frozenset((affidavit.id, filing.id)) in pair_ids
    assert frozenset((affidavit.id, same_document.id)) not in pair_ids

def configure_paid_gemini(monkeypatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(settings, "gemini_model", "gemini-3.8-flash")


def test_case_analysis_finds_source_linked_cross_document_date_conflict(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", StubGeminiAnalyzer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")
    upload_docx(client, case["id"], "court-filing.docx", "The notice was served on 13 March 2024.")

    started = client.post(f"/api/v1/cases/{case['id']}/analysis")
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest")

    assert started.status_code == 202
    assert result.status_code == 200
    body = result.json()
    assert body["run"]["status"] == "completed"
    assert body["run"]["document_count"] == 2
    assert body["run"]["fact_count"] == 2
    assert body["run"]["finding_count"] == 1
    assert body["run"]["retrieval_metadata"]["method"] == "lexical_fallback"
    assert body["run"]["retrieval_metadata"]["candidate_pairs_sent"] == 1
    finding = body["findings"][0]
    assert finding["finding_type"] == "contradiction"
    assert {
        finding["left_fact"]["source_filename"],
        finding["right_fact"]["source_filename"],
    } == {"affidavit.docx", "court-filing.docx"}
    assert finding["left_fact"]["source_locator"] == "Paragraph 1"
    assert finding["right_fact"]["source_locator"] == "Paragraph 1"
    for fact in (finding["left_fact"], finding["right_fact"]):
        assert fact["source_start_char"] == 0
        assert fact["source_end_char"] == len(fact["evidence_quote"])
        assert "page_num" in fact
    assert finding["left_fact"]["source_document_id"] != finding["right_fact"]["source_document_id"]
    assert body["run"]["claim_review_count"] == 2
    assert any(item["item_kind"] == "sentence" for item in body["extraction_items"])
    assert any(item["item_kind"] == "entity" and item["text"] == "notice" for item in body["extraction_items"])
    entity_item = next(item for item in body["extraction_items"] if item["item_kind"] == "entity" and item["text"] == "notice")
    assert entity_item["source_start_char"] == 4
    assert entity_item["source_end_char"] == 10
    assert "page_num" in entity_item
    assert any(item["item_kind"] == "date" and item["normalized_value"] == "2024-03-12" for item in body["extraction_items"])
    document_claims = [review for review in body["claim_reviews"] if review["claim_kind"] == "document"]
    assert len(document_claims) == 2
    assert all(review["support_status"] == "partially_supported" for review in document_claims)
    assert all(review["is_overstated"] for review in document_claims)
    assert all(review["evidence"] for review in document_claims)


def test_advocate_can_review_finding_and_save_extraction_correction(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", StubGeminiAnalyzer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")
    upload_docx(client, case["id"], "filing.docx", "The notice was served on 13 March 2024.")
    client.post(f"/api/v1/cases/{case['id']}/analysis")
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest").json()
    run_id = result["run"]["id"]
    finding = result["findings"][0]
    item = next(entry for entry in result["extraction_items"] if entry["item_kind"] == "sentence")

    finding_review = client.put(f"/api/v1/cases/{case['id']}/analysis/{run_id}/reviews", json={
        "target_kind": "finding", "target_id": finding["id"], "status": "not_a_contradiction", "note": "Different notices are described in context.",
    })
    item_review = client.put(f"/api/v1/cases/{case['id']}/analysis/{run_id}/reviews", json={
        "target_kind": "extraction_item", "target_id": item["id"], "status": "corrected", "correction_text": "Advocate corrected classification: disputed fact", "correction_category": "issue",
    })

    assert finding_review.status_code == 200
    assert item_review.status_code == 200
    latest = client.get(f"/api/v1/cases/{case['id']}/analysis/latest").json()
    assert latest["findings"][0]["review_status"] == "not_a_contradiction"
    assert {entry["target_kind"] for entry in latest["advocate_reviews"]} == {"finding", "extraction_item"}


def test_case_analysis_checks_advocate_claims_with_source_linked_evidence(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", StubGeminiAnalyzer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")
    upload_docx(client, case["id"], "court-filing.docx", "The notice was served on 13 March 2024.")

    started = client.post(
        f"/api/v1/cases/{case['id']}/analysis",
        json={"advocate_claims": ["The notice was served before the deadline."]},
    )
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest")

    assert started.status_code == 202
    assert result.status_code == 200
    body = result.json()
    advocate_reviews = [review for review in body["claim_reviews"] if review["claim_kind"] == "advocate"]
    assert len(advocate_reviews) == 1
    assert advocate_reviews[0]["claim_text"] == "The notice was served before the deadline."
    assert advocate_reviews[0]["support_status"] == "partially_supported"
    assert advocate_reviews[0]["evidence"]
    assert body["run"]["claim_review_count"] == 3


def test_case_analysis_marks_unmatched_claim_inconclusive(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", StubGeminiAnalyzer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")

    started = client.post(
        f"/api/v1/cases/{case['id']}/analysis",
        json={"advocate_claims": ["The payment was received in full."]},
    )
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest")

    assert started.status_code == 202
    unmatched = next(review for review in result.json()["claim_reviews"] if review["claim_kind"] == "advocate")
    assert unmatched["support_status"] == "partially_supported"
    assert unmatched["evidence"] == []
    assert "does not show" in unmatched["explanation"]


def test_free_tier_is_available_for_local_test_mode(client, monkeypatch) -> None:
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")
    monkeypatch.setattr(settings, "gemini_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "free")
    monkeypatch.setattr(settings, "app_env", "development")

    status_response = client.get(f"/api/v1/cases/{case['id']}/analysis/config")

    assert status_response.status_code == 200
    assert status_response.json()["ready"] is True
    assert "synthetic" in status_response.json()["message"]


def test_free_tier_is_disabled_outside_local_test_mode(client, monkeypatch) -> None:
    case = create_case(client)
    monkeypatch.setattr(settings, "gemini_api_key", "unit-test-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "free")
    monkeypatch.setattr(settings, "app_env", "production")

    status_response = client.get(f"/api/v1/cases/{case['id']}/analysis/config")

    assert status_response.status_code == 200
    assert status_response.json()["ready"] is False
    assert "disabled" in status_response.json()["message"]


def test_analysis_rejects_facts_with_unverifiable_source_quotes(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)

    class HallucinatingAnalyzer(StubGeminiAnalyzer):
        def extract_facts(self, sources) -> ExtractedFactBatch:
            return ExtractedFactBatch(
                facts=[
                    ExtractedFact(
                        source_unit_id=sources[0].source_unit_id,
                        fact_type="date",
                        topic_key="notice_service_date",
                        statement="A fabricated date was stated.",
                        evidence_quote="This text does not appear in the document.",
                        normalized_value="1 January 1900",
                        confidence=1,
                    )
                ]
            )

    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", HallucinatingAnalyzer)
    case = create_case(client)
    upload_docx(client, case["id"], "affidavit.docx", "The notice was served on 12 March 2024.")

    client.post(f"/api/v1/cases/{case['id']}/analysis")
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest")

    assert result.status_code == 200
    assert result.json()["facts"] == []
    assert result.json()["findings"] == []


def test_rule_indicators_remain_available_when_gemini_analysis_fails(client, monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)

    class UnavailableAnalyzer(StubGeminiAnalyzer):
        def extract_facts(self, sources):
            raise RuntimeError("provider temporarily unavailable")

    monkeypatch.setattr(case_analysis_processing, "GeminiCaseAnalyzer", UnavailableAnalyzer)
    case = create_case(client)
    upload_docx(
        client,
        case["id"],
        "complaint.docx",
        "The complaint invokes Section 138 of the Negotiable Instruments Act and claims Rs. 50,000/- was due on 12 March 2024.",
    )

    client.post(f"/api/v1/cases/{case['id']}/analysis")
    result = client.get(f"/api/v1/cases/{case['id']}/analysis/latest")

    assert result.status_code == 200
    body = result.json()
    assert body["run"]["status"] == "failed"
    assert any(item["item_kind"] == "amount" for item in body["extraction_items"])
    assert any(item["item_kind"] == "date" for item in body["extraction_items"])
    assert any(item["category"] == "section_or_rule" for item in body["extraction_items"])


def test_gemini_sdk_adapter_uses_json_schema_without_network(monkeypatch) -> None:
    configure_paid_gemini(monkeypatch)
    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)

            class Response:
                text = '{"facts": [], "findings": []}'

            return Response()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(genai, "Client", lambda **kwargs: FakeClient())
    analyzer = GeminiCaseAnalyzer()
    result = analyzer.extract_facts(
        [
            SourceText(
                source_unit_id=uuid4(),
                document_name="filing.docx",
                locator="Paragraph 1",
                text="A sample case passage.",
            )
        ]
    )

    assert result.facts == []
    assert calls[0]["model"] == "gemini-3.8-flash"
    assert calls[0]["config"].response_mime_type == "application/json"
    assert calls[0]["config"].response_schema["type"] == "OBJECT"
    assert set(calls[0]["config"].response_schema["required"]) == {
        "facts", "sentences", "entities", "legal_references"
    }
    assert calls[0]["config"].temperature is None
    assert "A sample case passage." in calls[0]["contents"]
    assert "filing.docx" not in calls[0]["contents"]
    assert "Paragraph 1" not in calls[0]["contents"]

    analyzer.compare_facts(
        [
            FactForComparison(
                fact_id=uuid4(),
                source_document_ref="doc_1",
                fact_type="date",
                topic_key="notice_service_date",
                statement="The notice was served on 12 March 2024.",
                evidence_quote="The notice was served on 12 March 2024.",
                normalized_value="12 March 2024",
            )
        ]
    )
    assert calls[1]["config"].response_schema["type"] == "OBJECT"
    assert "findings" in calls[1]["config"].response_schema["required"]
    assert "doc_1" in calls[1]["contents"]
