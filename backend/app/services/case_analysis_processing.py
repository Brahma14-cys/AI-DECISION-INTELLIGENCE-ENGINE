from collections import defaultdict
from datetime import UTC, datetime
import logging
import re
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.db.models import (
    Case,
    CaseAnalysisFact,
    CaseAnalysisFinding,
    CaseAnalysisExtractionItem,
    CaseAnalysisRun,
    CaseAnalysisReview,
    CaseClaimReview,
    CaseClaimReviewEvidence,
    CaseDocument,
    DocumentTextUnit,
)
from app.services.gemini_analysis import (
    ClaimForAssessment,
    ExtractedFactBatch,
    FactForComparison,
    GeminiCaseAnalyzer,
    SourceText,
    StructuredExtractionItem,
)


logger = logging.getLogger(__name__)
from app.services.legal_extraction_rules import extract_rule_based_indicators
from app.services.legal_ner import extract_legal_entities
from app.services.sentence_role_classifier import classify_sentence_roles
from app.services.case_semantic_retrieval import (
    MAX_SEMANTIC_FACTS_PER_RUN,
    MAX_SEMANTIC_NEIGHBORS_PER_FACT,
    SEMANTIC_SIMILARITY_THRESHOLD,
    select_embedding_facts,
    semantic_candidate_pairs,
)


MAX_SOURCE_SEGMENT_CHARS = 8_000
MAX_FACT_BATCH_CHARS = 24_000
# Structured output grows with each source sentence (facts, entities, legal
# references, and sentence labels). Keep batches small enough to avoid truncated
# Gemini JSON responses on document-dense judgments.
MAX_SOURCE_ITEMS_PER_BATCH = 50
MAX_COMPARISON_PAIRS_PER_FACT = 12
MAX_COMPARISON_PAIRS_PER_REQUEST = 80
MAX_TERM_POSTING_SIZE = 120
MAX_EMBEDDING_BATCH_SIZE = 40
MIN_FACT_CONFIDENCE_FOR_COMPARISON = 0.45
MAX_CLAIMS_PER_ASSESSMENT = 12
MAX_MANUAL_EVIDENCE_FACTS = 25
_STOP_WORDS = {
    "about", "after", "against", "also", "among", "been", "before", "being", "between",
    "both", "could", "does", "from", "have", "into", "more", "other", "over", "same",
    "should", "that", "their", "there", "these", "they", "this", "those", "through", "under",
    "upon", "were", "what", "when", "where", "which", "while", "with", "would", "your",
}
_LEGAL_GENERIC_TERMS = {
    "alleged", "alleges", "allegation", "applicant", "application", "court", "document",
    "evidence", "filed", "filing", "matter", "party", "petitioner", "record", "respondent",
    "said", "states", "stated", "submit", "submitted", "thereof", "herein", "whereas",
}


def gemini_is_ready() -> bool:
    tier = settings.gemini_data_tier.strip().lower()
    paid_enabled = tier == "paid"
    free_dev_test = tier == "free" and settings.app_env.strip().lower() in {"development", "test"}
    return bool(settings.gemini_api_key and (paid_enabled or free_dev_test))


def gemini_readiness_message() -> str:
    if not settings.gemini_api_key:
        return "Add GEMINI_API_KEY in backend/.env to enable Gemini analysis."
    tier = settings.gemini_data_tier.strip().lower()
    if tier == "free" and settings.app_env.strip().lower() in {"development", "test"}:
        return "Free-tier test mode is enabled for local development. Use synthetic or fully redacted documents only; Google may use free-tier prompts and responses to improve its products."
    if tier != "paid":
        return "Analysis is disabled. Use GEMINI_DATA_TIER=paid for normal analysis, or free only in local development/test mode with synthetic data."
    return "Configured for a paid Gemini project. Confirm the key belongs to a billing-enabled project."


_NON_BOUNDARY_PERIODS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "hon'ble.", "hon’ble.", "no.", "nos.",
    "sec.", "secs.", "art.", "arts.", "s.", "u.s.", "vs.", "v.", "e.g.", "i.e.", "rs.",
}


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return trimmed sentence spans in the original text, preserving offsets."""
    boundaries: list[int] = []
    for match in re.finditer(r"[.!?][\"')\]]*\s+|\n{2,}", text):
        punctuation_end = match.start() + 1
        if text[match.start()] in ".!?":
            punctuation_end = match.start() + len(match.group().rstrip())
            prefix = text[:match.start() + 1].rstrip()
            token = prefix.split()[-1].casefold() if prefix.split() else ""
            # A decimal point is not a sentence terminator.
            decimal = (
                text[match.start()] == "."
                and match.start() > 0
                and match.start() + 1 < len(text)
                and text[match.start() - 1].isdigit()
                and text[match.start() + 1].isdigit()
            )
            if decimal or token in _NON_BOUNDARY_PERIODS:
                continue
            boundaries.append(punctuation_end)
        else:
            boundaries.append(match.start())

    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in boundaries:
        end = boundary
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))
        start = boundary
    while start < len(text) and text[start].isspace():
        start += 1
    end = len(text.rstrip())
    if end > start:
        spans.append((start, end))
    return spans


def _split_source(source: SourceText) -> list[SourceText]:
    """Segment into sentence passages, bounding unusually long sentences safely."""
    spans = [
        part
        for start, end in _sentence_spans(source.text)
        for part in _bounded_sentence_spans(source.text, start, end)
    ]
    if not spans:
        return []
    return [
        source.model_copy(update={
            "source_unit_id": uuid4(),
            "text": source.text[start:end],
            "source_start_char": source.source_start_char + start,
        })
        for start, end in spans
    ]


def _bounded_sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Keep provider passages within the schema limit, preferring legal punctuation."""
    spans: list[tuple[int, int]] = []
    while end - start > MAX_SOURCE_SEGMENT_CHARS:
        limit = start + MAX_SOURCE_SEGMENT_CHARS
        # Split at the last clause/list boundary within the safe window, otherwise
        # at whitespace. An unbroken token longer than the provider limit is hard-
        # split at the limit; Python offsets remain code-point based and contiguous.
        matches = list(re.finditer(r"[;:\n]\s+|\s+", text[start:limit]))
        boundary = start + matches[-1].end() if matches else limit
        if boundary <= start:
            boundary = limit
        cut = boundary
        while cut > start and text[cut - 1].isspace():
            cut -= 1
        if cut == start:
            cut = boundary
        spans.append((start, cut))
        start = boundary
        while start < end and text[start].isspace():
            start += 1
    if end > start:
        spans.append((start, end))
    return spans


def _batch_sources(sources: list[SourceText]) -> list[list[SourceText]]:
    batches: list[list[SourceText]] = []
    current: list[SourceText] = []
    count = 0
    # Inputs are already sentence-segmented so their provider IDs remain aligned
    # with the source-unit and character-offset maps built by the caller.
    for source in sources:
        if current and (
            count + len(source.text) > MAX_FACT_BATCH_CHARS
            or len(current) >= MAX_SOURCE_ITEMS_PER_BATCH
        ):
            batches.append(current)
            current = []
            count = 0
        current.append(source)
        count += len(source.text)
    if current:
        batches.append(current)
    return batches


def _comparison_terms(fact: CaseAnalysisFact) -> set[str]:
    return {
        token for token in _claim_terms(
            f"{fact.topic_key} {fact.fact_type} {fact.statement} {fact.evidence_quote}"
        ) if token not in _LEGAL_GENERIC_TERMS
    }


def _normalized_topic(fact: CaseAnalysisFact) -> str:
    return " ".join(fact.topic_key.casefold().split())


def _comparison_value(fact: CaseAnalysisFact) -> str:
    value = fact.normalized_value or ""
    return " ".join(
        "".join(char.casefold() if char.isalnum() else " " for char in value).split()
    )


def _fact_pair_candidates(
    facts: list[CaseAnalysisFact],
    unit_map: dict[UUID, tuple[DocumentTextUnit, CaseDocument]] | None = None,
) -> list[tuple[CaseAnalysisFact, CaseAnalysisFact]]:
    """Retrieve plausible cross-document pairs without requiring identical topic keys.

    This is a local lexical candidate stage, not semantic proof. Exact topic/value
    matches are retained; otherwise a pair needs multiple case-specific shared
    terms (or one rare shared term) before it is sent to Gemini for adjudication.
    Per-fact caps keep a large case from creating an unbounded quadratic request.
    """
    eligible = [fact for fact in facts if fact.effective_confidence >= MIN_FACT_CONFIDENCE_FOR_COMPARISON]
    if len(eligible) < 2:
        return []

    def get_doc_id(fact: CaseAnalysisFact) -> UUID | None:
        if unit_map and fact.source_text_unit_id in unit_map:
            return unit_map[fact.source_text_unit_id][1].id
        source_unit = getattr(fact, "source_unit", None)
        return getattr(source_unit, "document_id", None) if source_unit else None

    terms_by_id = {fact.id: _comparison_terms(fact) for fact in eligible}
    topic_by_id = {fact.id: _normalized_topic(fact) for fact in eligible}
    value_by_id = {fact.id: _comparison_value(fact) for fact in eligible}
    docs_by_term: dict[str, set[UUID]] = defaultdict(set)
    for fact in eligible:
        for term in terms_by_id[fact.id]:
            docs_by_term[term].add(fact.id)

    possible: set[tuple[UUID, UUID]] = set()
    by_topic: dict[str, list[CaseAnalysisFact]] = defaultdict(list)
    by_value: dict[tuple[str, str], list[CaseAnalysisFact]] = defaultdict(list)
    for fact in eligible:
        if topic_by_id[fact.id]:
            by_topic[topic_by_id[fact.id]].append(fact)
        value = value_by_id[fact.id]
        if value and fact.fact_type:
            by_value[(fact.fact_type.casefold(), value)].append(fact)

    def add_cross_document_pairs(group: list[CaseAnalysisFact]) -> None:
        by_document: dict[UUID, list[CaseAnalysisFact]] = defaultdict(list)
        for fact in group:
            doc_id = get_doc_id(fact)
            if doc_id:
                by_document[doc_id].append(fact)
        # Keep the strongest facts per source document as a pool, then cap peers
        # per fact. The number of candidates therefore grows linearly with facts.
        candidate_pool = [
            fact
            for document_facts in by_document.values()
            for fact in sorted(document_facts, key=lambda item: item.effective_confidence, reverse=True)[
                :MAX_COMPARISON_PAIRS_PER_FACT
            ]
        ]
        candidate_pool.sort(key=lambda item: item.effective_confidence, reverse=True)
        for left in group:
            left_doc = get_doc_id(left)
            selected = 0
            for right in candidate_pool:
                if left_doc is not None and left_doc == get_doc_id(right):
                    continue
                possible.add(tuple(sorted((left.id, right.id), key=str)))
                selected += 1
                if selected >= MAX_COMPARISON_PAIRS_PER_FACT:
                    break

    for group in by_topic.values():
        add_cross_document_pairs(group)
    for group in by_value.values():
        add_cross_document_pairs(group)

    # Build candidate pairs through an inverted index, avoiding a full all-pairs
    # scan for cases containing many extracted facts.
    postings: dict[str, list[CaseAnalysisFact]] = defaultdict(list)
    for fact in eligible:
        for term in terms_by_id[fact.id]:
            postings[term].append(fact)
    shared_term_counts: dict[tuple[UUID, UUID], int] = defaultdict(int)
    rare_shared_pairs: set[tuple[UUID, UUID]] = set()
    for term, posting in postings.items():
        if len(posting) < 2:
            continue
        if len(posting) > MAX_TERM_POSTING_SIZE:
            by_document: dict[UUID, list[CaseAnalysisFact]] = defaultdict(list)
            for fact in posting:
                doc_id = get_doc_id(fact)
                if doc_id:
                    by_document[doc_id].append(fact)
            bounded_posting = [
                fact
                for document_facts in by_document.values()
                for fact in sorted(document_facts, key=lambda item: item.effective_confidence, reverse=True)[:2]
            ]
            bounded_posting.sort(key=lambda item: item.effective_confidence, reverse=True)
            posting = bounded_posting[:MAX_TERM_POSTING_SIZE]
        for index, left in enumerate(posting):
            left_doc = get_doc_id(left)
            for right in posting[index + 1:]:
                if left_doc is not None and left_doc == get_doc_id(right):
                    continue
                pair = tuple(sorted((left.id, right.id), key=str))
                shared_term_counts[pair] += 1
                if len(docs_by_term[term]) <= 3:
                    rare_shared_pairs.add(pair)
    for pair, shared_count in shared_term_counts.items():
        if shared_count >= 2 or pair in rare_shared_pairs:
            possible.add(pair)

    facts_by_id = {fact.id: fact for fact in eligible}
    scored: list[tuple[float, UUID, UUID]] = []
    for left_id, right_id in possible:
        left, right = facts_by_id[left_id], facts_by_id[right_id]
        shared = terms_by_id[left_id] & terms_by_id[right_id]
        idf_score = sum(1.0 + (len(eligible) / (1 + len(docs_by_term[token]))) for token in shared)
        score = idf_score + (8.0 if topic_by_id[left_id] and topic_by_id[left_id] == topic_by_id[right_id] else 0.0)
        score += 6.0 if value_by_id[left_id] and value_by_id[left_id] == value_by_id[right_id] else 0.0
        score += min(left.effective_confidence, right.effective_confidence)
        scored.append((score, left_id, right_id))

    # Keep the strongest candidates for each fact, then union the selected edges.
    # This preserves recall across multiple opposing documents while bounding calls.
    per_fact: dict[UUID, list[tuple[float, UUID]]] = defaultdict(list)
    for score, left_id, right_id in scored:
        per_fact[left_id].append((score, right_id))
        per_fact[right_id].append((score, left_id))
    selected: set[tuple[UUID, UUID]] = set()
    for fact_id, candidates in per_fact.items():
        for _, peer_id in sorted(candidates, key=lambda item: (item[0], str(item[1])), reverse=True)[:MAX_COMPARISON_PAIRS_PER_FACT]:
            selected.add(tuple(sorted((fact_id, peer_id), key=str)))
    return [(facts_by_id[left], facts_by_id[right]) for left, right in sorted(selected, key=lambda pair: (str(pair[0]), str(pair[1])))]


def _claim_terms(text: str) -> set[str]:
    return {
        token for token in "".join(char.casefold() if char.isalnum() else " " for char in text).split()
        if len(token) > 3 and token not in _STOP_WORDS
    }


def _manual_claim_candidates(claim: str, facts: list[CaseAnalysisFact]) -> list[CaseAnalysisFact]:
    terms = _claim_terms(claim)
    document_frequency: dict[str, int] = defaultdict(int)
    fact_terms = {fact.id: _comparison_terms(fact) for fact in facts}
    for indexed_terms in fact_terms.values():
        for term in indexed_terms:
            document_frequency[term] += 1
    ranked: list[tuple[float, float, CaseAnalysisFact]] = []
    for fact in facts:
        overlap = terms & fact_terms[fact.id]
        if overlap:
            # Inverse document frequency demotes generic words and prioritizes
            # uncommon names, dates, and event terms among this case's evidence.
            score = sum(1.0 + len(facts) / (1 + document_frequency[term]) for term in overlap)
            if _normalized_topic(fact) and _normalized_topic(fact) in claim.casefold():
                score += 2.0
            ranked.append((score, fact.effective_confidence, fact))
    return [fact for _, _, fact in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True)[:MAX_MANUAL_EVIDENCE_FACTS]]


def _semantic_candidate_pairs(
    facts: list[CaseAnalysisFact],
    analyzer: GeminiCaseAnalyzer,
) -> tuple[list[tuple[CaseAnalysisFact, CaseAnalysisFact]], dict]:
    eligible = [fact for fact in facts if fact.effective_confidence >= MIN_FACT_CONFIDENCE_FOR_COMPARISON]
    report = {
        "status": "not_configured",
        "facts_total": len(facts),
        "facts_eligible": len(eligible),
        "facts_embedded": 0,
        "semantic_candidate_pairs": 0,
        "similarity_threshold": SEMANTIC_SIMILARITY_THRESHOLD,
        "truncated": len(eligible) > MAX_SEMANTIC_FACTS_PER_RUN,
        "warning": "Semantic retrieval was unavailable; lexical candidate matching was used.",
    }
    embed = getattr(analyzer, "embed_similarity_texts", None)
    if not eligible:
        report["status"] = "skipped_no_eligible_facts"
        report["warning"] = "No extracted facts met the minimum confidence threshold for cross-document comparison."
        return [], report
    if not callable(embed):
        return [], report

    selected = select_embedding_facts(eligible)
    texts = [
        f"Topic: {fact.topic_key}. Type: {fact.fact_type}. Assertion: {fact.statement}. Source quote: {fact.evidence_quote}"
        for fact in selected
    ]
    try:
        vectors: list[list[float]] = []
        for batch in _chunks(texts, MAX_EMBEDDING_BATCH_SIZE):
            vectors.extend(embed(batch))
        pairs = semantic_candidate_pairs(selected, vectors)
    except Exception as error:  # noqa: BLE001 — lexical retrieval remains the safe fallback.
        report["status"] = "fallback"
        report["warning"] = f"Semantic retrieval failed ({type(error).__name__}); lexical candidate matching was used."
        return [], report

    report.update({
        "status": "complete" if not report["truncated"] else "partial",
        "facts_embedded": len(selected),
        "semantic_candidate_pairs": len(pairs),
        "warning": (
            "Semantic retrieval screened a confidence-ranked subset of facts; this run may omit relationships involving unembedded facts."
            if report["truncated"]
            else "Candidate retrieval is a screening step, not proof that every relationship or contradiction was found."
        ),
    })
    return pairs, report


def _provider_fact(
    fact: CaseAnalysisFact,
    document_refs: dict[UUID, str],
    unit_map: dict[UUID, tuple[DocumentTextUnit, CaseDocument]] | None = None,
    provider_id: UUID | None = None,
) -> FactForComparison:
    if unit_map and fact.source_text_unit_id in unit_map:
        unit, doc = unit_map[fact.source_text_unit_id]
        doc_ref = document_refs.get(doc.id, "doc_1")
        ocr_conf = unit.ocr_confidence
        ocr_review = (ocr_conf is not None and ocr_conf < settings.ocr_review_confidence_threshold)
    else:
        source_unit = getattr(fact, "source_unit", None)
        doc_id = getattr(source_unit, "document_id", None) if source_unit else None
        doc_ref = document_refs.get(doc_id, "doc_1") if doc_id else "doc_1"
        ocr_conf = getattr(source_unit, "ocr_confidence", None)
        ocr_review = getattr(fact, "ocr_needs_review", False)

    return FactForComparison(
        fact_id=provider_id or uuid4(),
        source_document_ref=doc_ref,
        fact_type=fact.fact_type,
        topic_key=fact.topic_key,
        statement=fact.statement,
        evidence_quote=fact.evidence_quote,
        normalized_value=fact.normalized_value,
        source_ocr_confidence=ocr_conf,
        ocr_needs_review=ocr_review,
    )


def _persist_extraction_items(
    db,
    analysis_run_id: UUID,
    items: list[StructuredExtractionItem],
    source_unit_id_map: dict[UUID, UUID],
    source_text_by_id: dict[UUID, str],
    source_start_by_id: dict[UUID, int],
    seen_items: set[tuple[UUID, str, str, int]],
    next_occurrence_by_key: dict[tuple[UUID, str, str, str, str], int],
) -> None:
    for item in items:
        local_unit_id = source_unit_id_map.get(item.source_unit_id)
        original_text = source_text_by_id.get(item.source_unit_id, "")
        quote = item.evidence_quote.strip()
        extracted_text = item.text.strip()
        occurrence_key = (local_unit_id, item.item_kind, item.category, extracted_text.casefold(), item.extractor)
        item_span = _find_source_span_range(original_text, extracted_text, next_occurrence_by_key.get(occurrence_key, 0))
        if (
            local_unit_id is None
            or not quote
            or quote.casefold() not in original_text.casefold()
            or not extracted_text
            or extracted_text.casefold() not in original_text.casefold()
        ):
            continue
        item_start = item_span[0] if item_span is not None else None
        item_end = item_span[1] if item_span is not None else None
        key = (local_unit_id, item.item_kind, item.category, item_start if item_start is not None else -1)
        if key in seen_items:
            continue
        seen_items.add(key)
        if item_end is not None:
            next_occurrence_by_key[occurrence_key] = item_end
        db.add(
            CaseAnalysisExtractionItem(
                analysis_run_id=analysis_run_id,
                source_text_unit_id=local_unit_id,
                item_kind=item.item_kind,
                category=item.category,
                text=extracted_text,
                normalized_value=item.normalized_value,
                legal_role=item.legal_role,
                evidence_quote=quote,
                confidence=item.confidence,
                extractor=item.extractor,
                source_start_char=(source_start_by_id[item.source_unit_id] + item_start if item_start is not None else None),
                source_end_char=(source_start_by_id[item.source_unit_id] + item_end if item_end is not None else None),
            )
        )


def _find_source_span(source: str, needle: str, start: int = 0) -> int | None:
    """Return the start of the next exact or case-insensitive source mention."""
    span = _find_source_span_range(source, needle, start)
    return span[0] if span is not None else None


def _find_source_span_range(source: str, needle: str, start: int = 0) -> tuple[int, int] | None:
    if not needle:
        return None
    exact = source.find(needle, start)
    if exact >= 0:
        return exact, exact + len(needle)
    # Build an index from casefolded characters back to original offsets; casefold
    # can expand characters (for example, German sharp s) so lengths may differ.
    folded_chars: list[str] = []
    original_offsets: list[int] = []
    for offset, character in enumerate(source):
        folded_character = character.casefold()
        folded_chars.extend(folded_character)
        original_offsets.extend([offset] * len(folded_character))
    folded_source = "".join(folded_chars)
    folded_needle = needle.casefold()
    folded_start = next((index for index, offset in enumerate(original_offsets) if offset >= start), len(folded_source))
    folded_index = folded_source.find(folded_needle, folded_start)
    if folded_index < 0:
        return None
    folded_end = folded_index + len(folded_needle) - 1
    # Do not accept a partial match inside a character whose casefold expands
    # (e.g. matching one "s" inside the casefold of "ß").
    if folded_index > 0 and original_offsets[folded_index - 1] == original_offsets[folded_index]:
        return None
    if folded_end + 1 < len(original_offsets) and original_offsets[folded_end + 1] == original_offsets[folded_end]:
        return None
    return original_offsets[folded_index], original_offsets[folded_end] + 1


def _model_extraction_items(result: ExtractedFactBatch) -> list[StructuredExtractionItem]:
    items = [
        StructuredExtractionItem(
            source_unit_id=sentence.source_unit_id,
            item_kind="sentence",
            category=sentence.classification,
            text=sentence.sentence,
            evidence_quote=sentence.sentence,
            confidence=sentence.confidence,
            extractor="gemini",
        )
        for sentence in result.sentences
    ]
    items.extend(
        StructuredExtractionItem(
            source_unit_id=entity.source_unit_id,
            item_kind="entity",
            category=entity.entity_type,
            text=entity.entity_text,
            normalized_value=entity.canonical_name,
            legal_role=entity.legal_role,
            evidence_quote=entity.evidence_quote,
            confidence=entity.confidence,
            extractor="gemini",
        )
        for entity in result.entities
    )
    items.extend(
        StructuredExtractionItem(
            source_unit_id=reference.source_unit_id,
            item_kind="legal_reference",
            category=reference.reference_type,
            text=reference.reference_text,
            normalized_value=reference.normalized_reference,
            evidence_quote=reference.evidence_quote,
            confidence=reference.confidence,
            extractor="gemini",
        )
        for reference in result.legal_references
    )
    return items


def _chunks(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def process_case_analysis(analysis_run_id: UUID, advocate_claims: list[str] | None = None) -> None:
    """Analyze a case asynchronously and persist only source-validated model output."""
    with SessionLocal() as db:
        run = db.get(CaseAnalysisRun, analysis_run_id)
        if run is None:
            return
        # The persistent queue may recover this run after a process crash. Clear
        # any partial results first so retrying the durable job is idempotent.
        db.execute(delete(CaseAnalysisReview).where(CaseAnalysisReview.analysis_run_id == run.id))
        db.execute(delete(CaseAnalysisFinding).where(CaseAnalysisFinding.analysis_run_id == run.id))
        db.execute(delete(CaseClaimReview).where(CaseClaimReview.analysis_run_id == run.id))
        db.execute(delete(CaseAnalysisFact).where(CaseAnalysisFact.analysis_run_id == run.id))
        db.execute(delete(CaseAnalysisExtractionItem).where(CaseAnalysisExtractionItem.analysis_run_id == run.id))
        run.status = "processing"
        run.model = settings.gemini_model
        run.error_message = None
        run.retrieval_metadata = None
        db.commit()

        try:
            rows = db.execute(
                select(DocumentTextUnit, CaseDocument)
                .join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
                .where(
                    CaseDocument.case_id == run.case_id,
                    DocumentTextUnit.text != "",
                )
                .order_by(CaseDocument.uploaded_at, DocumentTextUnit.unit_number)
            ).all()
            unit_map: dict[UUID, tuple[DocumentTextUnit, CaseDocument]] = {
                unit.id: (unit, document) for unit, document in rows
            }
            source_unit_id_map: dict[UUID, UUID] = {}
            source_text_by_id: dict[UUID, str] = {}
            source_start_by_id: dict[UUID, int] = {}
            next_fact_occurrence_by_key: dict[tuple[UUID, str], int] = {}
            sources: list[SourceText] = []
            document_ids = list(dict.fromkeys(document.id for _, document in rows))
            source_document_ref = {document_id: f"doc_{i + 1}" for i, document_id in enumerate(document_ids)}
            for unit, document in rows:
                base_source = SourceText(
                    source_unit_id=uuid4(),
                    document_name=document.original_filename,
                    locator=unit.locator_label,
                    text=unit.text,
                    extraction_method=unit.extraction_method,
                    ocr_confidence=unit.ocr_confidence,
                )
                for sentence in _split_source(base_source):
                    source_unit_id_map[sentence.source_unit_id] = unit.id
                    source_text_by_id[sentence.source_unit_id] = sentence.text
                    source_start_by_id[sentence.source_unit_id] = sentence.source_start_char
                    sources.append(sentence)
            document_ids_with_text = {document.id for _, document in rows}
            run.document_count = len(document_ids_with_text)
            run.text_unit_count = len(sources)
            db.flush()

            analyzer = GeminiCaseAnalyzer()
            persisted_facts: list[CaseAnalysisFact] = []
            seen_extraction_items: set[tuple[UUID, str, str, int]] = set()
            next_occurrence_by_key: dict[tuple[UUID, str, str, str, str], int] = {}
            for batch in _batch_sources(sources):
                # Deterministic dates, amounts, and legal-reference patterns remain
                # available even when the hosted model is temporarily unavailable.
                local_items = [
                    item
                    for source in batch
                    for item in extract_rule_based_indicators(source)
                ]
                local_items.extend(
                    extract_legal_entities(batch)
                )
                # Keep the seven-way legal rhetorical role separate from Gemini's
                # case-specific fact / issue / irrelevant classification.
                local_items.extend(classify_sentence_roles(batch))
                _persist_extraction_items(
                    db,
                    run.id,
                    local_items,
                    source_unit_id_map,
                    source_text_by_id,
                    source_start_by_id,
                    seen_extraction_items,
                    next_occurrence_by_key,
                )
                db.commit()

                batch_result = analyzer.extract_facts(batch)
                _persist_extraction_items(
                    db,
                    run.id,
                    _model_extraction_items(batch_result),
                    source_unit_id_map,
                    source_text_by_id,
                    source_start_by_id,
                    seen_extraction_items,
                    next_occurrence_by_key,
                )
                allowed_source_ids = {source.source_unit_id for source in batch}
                for item in batch_result.facts:
                    if item.source_unit_id not in allowed_source_ids:
                        continue
                    original_text = source_text_by_id.get(item.source_unit_id, "")
                    if item.evidence_quote.strip().casefold() not in original_text.casefold():
                        continue
                    fact_quote = item.evidence_quote.strip()
                    fact_occurrence_key = (item.source_unit_id, fact_quote.casefold())
                    fact_span = _find_source_span_range(
                        original_text,
                        fact_quote,
                        next_fact_occurrence_by_key.get(fact_occurrence_key, 0),
                    )
                    fact_start = fact_span[0] if fact_span is not None else None
                    fact_end = fact_span[1] if fact_span is not None else None
                    if fact_end is not None:
                        next_fact_occurrence_by_key[fact_occurrence_key] = fact_end
                    fact = CaseAnalysisFact(
                        analysis_run_id=run.id,
                        source_text_unit_id=source_unit_id_map[item.source_unit_id],
                        fact_type=item.fact_type,
                        topic_key=" ".join(item.topic_key.strip().split())[:160],
                        statement=item.statement.strip(),
                        evidence_quote=item.evidence_quote.strip(),
                        normalized_value=item.normalized_value,
                        confidence=item.confidence,
                        source_start_char=(source_start_by_id[item.source_unit_id] + fact_start if fact_start is not None else None),
                        source_end_char=(source_start_by_id[item.source_unit_id] + fact_end if fact_end is not None else None),
                    )
                    db.add(fact)
                    persisted_facts.append(fact)
                db.flush()
            db.flush()

            seen_fact_pairs: set[tuple[UUID, UUID]] = set()
            lexical_pairs = _fact_pair_candidates(persisted_facts, unit_map)
            semantic_pairs, retrieval_metadata = _semantic_candidate_pairs(persisted_facts, analyzer)
            candidates_by_pair = {
                tuple(sorted((left.id, right.id), key=str)): (left, right)
                for left, right in [*lexical_pairs, *semantic_pairs]
            }
            candidate_pairs = list(candidates_by_pair.values())
            retrieval_metadata.update({
                "method": "hybrid_semantic_lexical" if retrieval_metadata["status"] in {"complete", "partial"} else "lexical_fallback",
                "lexical_candidate_pairs": len(lexical_pairs),
                "candidate_pairs_sent": len(candidate_pairs),
                "max_lexical_neighbors_per_fact": MAX_COMPARISON_PAIRS_PER_FACT,
                "max_semantic_neighbors_per_fact": MAX_SEMANTIC_NEIGHBORS_PER_FACT,
                "max_facts_per_embedding_run": MAX_SEMANTIC_FACTS_PER_RUN,
            })
            for pair_batch in _chunks(candidate_pairs, MAX_COMPARISON_PAIRS_PER_REQUEST):
                comparison_batch = list({
                    fact.id: fact for pair in pair_batch for fact in pair
                }.values())
                provider_fact_id_map = {fact.id: uuid4() for fact in comparison_batch}
                model_inputs = [
                    _provider_fact(fact, source_document_ref, unit_map, provider_fact_id_map[fact.id])
                    for fact in comparison_batch
                ]
                allowed_fact_ids = set(provider_fact_id_map.values())
                fact_by_provider_id = {
                    provider_fact_id_map[fact.id]: fact for fact in comparison_batch
                }
                provider_candidate_pairs = [
                    (provider_fact_id_map[left.id], provider_fact_id_map[right.id])
                    for left, right in pair_batch
                ]
                allowed_provider_pairs = {
                    tuple(sorted(pair, key=str)) for pair in provider_candidate_pairs
                }
                for item in analyzer.compare_facts(model_inputs, provider_candidate_pairs).findings:
                    if item.left_fact_id not in allowed_fact_ids or item.right_fact_id not in allowed_fact_ids:
                        continue
                    if tuple(sorted((item.left_fact_id, item.right_fact_id), key=str)) not in allowed_provider_pairs:
                        continue
                    left = fact_by_provider_id[item.left_fact_id]
                    right = fact_by_provider_id[item.right_fact_id]
                    if left.source_unit.document_id == right.source_unit.document_id:
                        continue
                    pair = tuple(sorted((left.id, right.id), key=str))
                    if pair in seen_fact_pairs:
                        continue
                    seen_fact_pairs.add(pair)
                    relation_label = item.relation_label
                    if item.finding_type == "relation" and relation_label is None:
                        relation_label = "related"
                    low_ocr_facts = [fact for fact in (left, right) if fact.ocr_needs_review]
                    explanation = item.explanation.strip()
                    if low_ocr_facts:
                        locations = ", ".join(f"{fact.source_filename} · {fact.source_locator}" for fact in low_ocr_facts)
                        explanation += f" At least one passage has low or unavailable OCR confidence ({locations}); verify both original documents before relying on this finding."
                    db.add(
                        CaseAnalysisFinding(
                            analysis_run_id=run.id,
                            finding_type=item.finding_type,
                            relation_label=relation_label,
                            left_fact_id=left.id,
                            right_fact_id=right.id,
                            explanation=explanation,
                            confidence=min(item.confidence, left.effective_confidence, right.effective_confidence),
                        )
                    )

            # Each extracted fact is checked against topically retrieved facts from
            # other documents. The source fact itself is never used as its own proof.
            assessment_inputs: list[tuple[UUID, str, CaseAnalysisFact | None, list[CaseAnalysisFact], UUID | None]] = []
            for fact in persisted_facts:
                candidates = _manual_claim_candidates(
                    fact.statement,
                    [
                        other for other in persisted_facts
                        if other.id != fact.id
                        and other.source_unit.document_id != fact.source_unit.document_id
                    ],
                )
                if candidates:
                    assessment_inputs.append((uuid4(), fact.statement, fact, candidates, fact.source_unit.document_id))
                else:
                    ocr_note = (
                        f" The source has low or unavailable OCR confidence ({fact.source_filename} · {fact.source_locator}); verify the original scan before relying on this assessment."
                        if fact.ocr_needs_review else ""
                    )
                    db.add(
                        CaseClaimReview(
                            analysis_run_id=run.id,
                            claim_kind="document",
                            claim_text=fact.statement,
                            source_fact_id=fact.id,
                            support_status="partially_supported",
                            explanation="No independent matching fact was retrieved from another uploaded document. This is not proof that the assertion is false; review the source documents manually." + ocr_note,
                            is_overstated=False,
                            overstatement_reason=None,
                        )
                    )

            for claim in advocate_claims or []:
                claim_id = uuid4()
                candidates = _manual_claim_candidates(claim, persisted_facts)
                if candidates:
                    assessment_inputs.append((claim_id, claim, None, candidates, None))
                else:
                    db.add(
                        CaseClaimReview(
                            analysis_run_id=run.id,
                            claim_kind="advocate",
                            claim_text=claim,
                            source_fact_id=None,
                            support_status="partially_supported",
                            explanation="No closely matching extracted facts were retrieved for this claim. This does not show that supporting evidence is absent; review the source documents manually.",
                            is_overstated=False,
                            overstatement_reason=None,
                        )
                    )

            pending_reviews = []
            for group in _chunks(assessment_inputs, MAX_CLAIMS_PER_ASSESSMENT):
                provider_claim_ids = {claim_id: uuid4() for claim_id, *_ in group}
                candidate_maps: dict[UUID, dict[UUID, CaseAnalysisFact]] = {}
                request_claims = []
                for claim_id, claim_text, source_fact, candidates, source_document_id in group:
                    fact_id_map = {fact.id: uuid4() for fact in candidates}
                    candidate_maps[provider_claim_ids[claim_id]] = {
                        fact_id_map[fact.id]: fact for fact in candidates
                    }
                    request_claims.append(
                        ClaimForAssessment(
                            claim_id=provider_claim_ids[claim_id],
                            claim_text=claim_text,
                            claim_source_document_ref=(
                                source_document_ref[source_document_id] if source_document_id is not None else None
                            ),
                            evidence_facts=[_provider_fact(fact, source_document_ref, unit_map, fact_id_map[fact.id]) for fact in candidates],
                        )
                    )
                result = analyzer.assess_claims(request_claims)
                returned_claims: set[UUID] = set()
                for item in result.assessments:
                    candidates_by_id = candidate_maps.get(item.claim_id)
                    if candidates_by_id is None or item.claim_id in returned_claims:
                        continue
                    returned_claims.add(item.claim_id)
                    original_claim_id = next(
                        (claim_id for claim_id, provider_id in provider_claim_ids.items() if provider_id == item.claim_id),
                        None,
                    )
                    if original_claim_id is None:
                        continue
                    original = next(entry for entry in group if entry[0] == original_claim_id)
                    _, claim_text, source_fact, _, _ = original
                    evidence_facts = [candidates_by_id[fact_id] for fact_id in item.evidence_fact_ids if fact_id in candidates_by_id]
                    # Never accept self-document support or uncited model evidence.
                    if source_fact is not None:
                        source_doc_id = unit_map[source_fact.source_text_unit_id][1].id if source_fact.source_text_unit_id in unit_map else None
                        evidence_facts = [
                            fact for fact in evidence_facts
                            if fact.source_text_unit_id in unit_map
                            and unit_map[fact.source_text_unit_id][1].id != source_doc_id
                        ]
                    status = item.support_status
                    explanation = item.explanation.strip()
                    if status == "supported" and not evidence_facts:
                        status = "partially_supported"
                        explanation += " No independently sourced supporting passage was returned, so this status is provisional."
                    ocr_review_facts = [
                        fact for fact in evidence_facts
                        if fact.source_text_unit_id in unit_map
                        and unit_map[fact.source_text_unit_id][0].ocr_confidence is not None
                        and unit_map[fact.source_text_unit_id][0].ocr_confidence < settings.ocr_review_confidence_threshold
                    ]
                    if source_fact is not None and source_fact.source_text_unit_id in unit_map and unit_map[source_fact.source_text_unit_id][0].ocr_confidence is not None and unit_map[source_fact.source_text_unit_id][0].ocr_confidence < settings.ocr_review_confidence_threshold:
                        ocr_review_facts.append(source_fact)
                    if ocr_review_facts:
                        if status in {"supported", "unsupported"}:
                            status = "partially_supported"
                        locations = ", ".join(
                            f"{fact.source_filename} · {fact.source_locator}"
                            for fact in ocr_review_facts[:3]
                        )
                        explanation += f" OCR review required before relying on this assessment: {locations}. Verify the original scan; OCR-derived evidence may contain recognition errors."
                    review = CaseClaimReview(
                        analysis_run_id=run.id,
                        claim_kind="document" if source_fact is not None else "advocate",
                        claim_text=claim_text,
                        source_fact_id=source_fact.id if source_fact is not None else None,
                        support_status=status,
                        explanation=explanation,
                        is_overstated=bool(
                            item.is_overstated
                            and evidence_facts
                            and item.overstatement_reason
                            and item.overstatement_reason.strip()
                        ),
                        overstatement_reason=(
                            item.overstatement_reason.strip()
                            if item.is_overstated and evidence_facts and item.overstatement_reason and item.overstatement_reason.strip()
                            else None
                        ),
                    )
                    db.add(review)
                    pending_reviews.append((review, evidence_facts))

                for provider_claim_id in candidate_maps:
                    if provider_claim_id in returned_claims:
                        continue
                    original_claim_id = next(
                        claim_id for claim_id, candidate_id in provider_claim_ids.items()
                        if candidate_id == provider_claim_id
                    )
                    _, claim_text, source_fact, _, _ = next(entry for entry in group if entry[0] == original_claim_id)
                    db.add(
                        CaseClaimReview(
                            analysis_run_id=run.id,
                            claim_kind="document" if source_fact is not None else "advocate",
                            claim_text=claim_text,
                            source_fact_id=source_fact.id if source_fact is not None else None,
                            support_status="partially_supported",
                            explanation="The model did not return a review for this claim. Review the relevant case documents manually.",
                            is_overstated=False,
                            overstatement_reason=None,
                        )
                    )

            db.flush()
            for review, evidence_facts in pending_reviews:
                for fact in evidence_facts:
                    db.add(CaseClaimReviewEvidence(claim_review_id=review.id, evidence_fact_id=fact.id))

            run.fact_count = len(persisted_facts)
            run.finding_count = len(seen_fact_pairs)
            db.flush()
            run.claim_review_count = db.scalar(
                select(func.count(CaseClaimReview.id)).where(CaseClaimReview.analysis_run_id == run.id)
            ) or 0
            run.status = "completed"
            run.retrieval_metadata = retrieval_metadata
            run.completed_at = datetime.now(UTC)
            case = db.get(Case, run.case_id)
            if case is not None:
                case.updated_at = datetime.now(UTC)
            db.commit()
            # Keep the automatic workflow moving after a successful analysis.
            # A source uploaded while this run was in progress takes priority:
            # enqueue a fresh analysis before building a graph for stale data.
            try:
                from app.services.case_workflow import (
                    enqueue_case_analysis_if_ready,
                    enqueue_case_graph_after_analysis,
                )

                newer_analysis_queued = enqueue_case_analysis_if_ready(db, run.case_id)
                if not newer_analysis_queued:
                    enqueue_case_graph_after_analysis(db, run)
            except Exception:  # noqa: BLE001 — the completed analysis remains usable if a downstream queue fails.
                db.rollback()
        except Exception as error:  # noqa: BLE001 — do not persist prompts, excerpts, or vendor error bodies.
            logger.error(
                "Case analysis failed run_id=%s error_type=%s",
                analysis_run_id,
                type(error).__name__,
            )
            db.rollback()
            failed_run = db.get(CaseAnalysisRun, analysis_run_id)
            if failed_run is None:
                return
            db.execute(delete(CaseAnalysisFinding).where(CaseAnalysisFinding.analysis_run_id == analysis_run_id))
            # Keep exact, deterministic regex indicators already committed for review.
            db.execute(
                delete(CaseClaimReviewEvidence).where(
                    CaseClaimReviewEvidence.claim_review_id.in_(
                        select(CaseClaimReview.id).where(CaseClaimReview.analysis_run_id == analysis_run_id)
                    )
                )
            )
            db.execute(delete(CaseClaimReview).where(CaseClaimReview.analysis_run_id == analysis_run_id))
            db.execute(delete(CaseAnalysisFact).where(CaseAnalysisFact.analysis_run_id == analysis_run_id))
            failed_run.status = "failed"
            failed_run.fact_count = 0
            failed_run.finding_count = 0
            failed_run.error_message = (
                "Analysis did not complete. Check the Gemini API key, paid-project setting, model access, and connectivity, then retry."
            )
            failed_run.completed_at = datetime.now(UTC)
            db.commit()
