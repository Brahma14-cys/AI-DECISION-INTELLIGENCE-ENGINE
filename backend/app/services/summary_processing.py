import re
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.db.models import Case, CaseDocument, CaseSummaryRun, DocumentTextUnit
from app.services.gemini_analysis import (
    CaseSummaryDraft,
    GeminiCaseAnalyzer,
    SourceText,
    SummaryCitation,
    SummaryPoint,
    SummarySection,
)


logger = logging.getLogger(__name__)


MAX_SUMMARY_SOURCE_CHARS = 8_000
MAX_SUMMARY_BATCH_CHARS = 24_000
MAX_REDUCTION_INPUT_CHARS = 60_000


def _split_sources(source: SourceText) -> list[SourceText]:
    if len(source.text) <= MAX_SUMMARY_SOURCE_CHARS:
        return [source]

    text = source.text
    segments: list[SourceText] = []
    start = 0
    while start < len(text):
        hard_end = min(start + MAX_SUMMARY_SOURCE_CHARS, len(text))
        if hard_end == len(text):
            end = hard_end
        else:
            preferred_start = start + MAX_SUMMARY_SOURCE_CHARS // 2
            paragraph_end = text.rfind("\n\n", preferred_start, hard_end)
            line_end = text.rfind("\n", preferred_start, hard_end)
            sentence_ends = [
                start + match.end()
                for match in re.finditer(r"[.!?]\s+", text[start:hard_end])
                if start + match.end() >= preferred_start
            ]
            whitespace_end = text.rfind(" ", preferred_start, hard_end)
            if paragraph_end >= 0:
                end = paragraph_end + 2
            elif sentence_ends:
                end = max(sentence_ends)
            elif line_end >= 0:
                end = line_end + 1
            elif whitespace_end > start:
                end = whitespace_end
            else:
                end = hard_end

        if end <= start:
            end = hard_end
        segments.append(source.model_copy(update={"text": text[start:end]}))
        start = end
    return segments


def _source_batches(sources: list[SourceText]) -> list[list[SourceText]]:
    batches: list[list[SourceText]] = []
    current: list[SourceText] = []
    char_count = 0
    for source in sources:
        for segment in _split_sources(source):
            if current and char_count + len(segment.text) > MAX_SUMMARY_BATCH_CHARS:
                batches.append(current)
                current = []
                char_count = 0
            current.append(segment)
            char_count += len(segment.text)
    if current:
        batches.append(current)
    return batches


def _draft_size(draft: CaseSummaryDraft) -> int:
    return len(draft.model_dump_json())


def _draft_groups(drafts: list[CaseSummaryDraft]) -> list[list[CaseSummaryDraft]]:
    if len(drafts) <= 1:
        return [drafts]
    groups: list[list[CaseSummaryDraft]] = []
    current: list[CaseSummaryDraft] = []
    size = 0
    for draft in drafts:
        draft_size = _draft_size(draft)
        if current and len(current) >= 2 and size + draft_size > MAX_REDUCTION_INPUT_CHARS:
            groups.append(current)
            current = []
            size = 0
        current.append(draft)
        size += draft_size
    if current:
        if len(groups) > 0 and len(current) == 1:
            groups[-1].append(current[0])
        else:
            groups.append(current)
    return groups


def _normalize_match_text(text: str) -> str:
    cleaned = re.sub(r"[\s\u200b\u00a0]+", " ", text)
    cleaned = re.sub(r"['\"“”‘’`]", "'", cleaned)
    cleaned = re.sub(r"[–—]", "-", cleaned)
    return cleaned.casefold().strip()


def _find_evidence_quote(quote: str, original: str) -> str | None:
    if not quote or not original:
        return None
    raw_quote = quote.strip().strip("'\"“”‘’")
    if not raw_quote:
        return None
    # 1. Exact or case-insensitive direct match
    if raw_quote.casefold() in original.casefold():
        idx = original.casefold().find(raw_quote.casefold())
        return original[idx:idx + len(raw_quote)]
    
    # 2. Normalized whitespace / punctuation match
    norm_quote = _normalize_match_text(raw_quote)
    norm_original = _normalize_match_text(original)
    if norm_quote in norm_original:
        return raw_quote

    # 3. Subsequence / token overlap: match key phrase if 3+ words match
    words = re.findall(r"[\w]+", norm_quote)
    if len(words) >= 3:
        for window_len in range(min(len(words), 8), 2, -1):
            subphrase = " ".join(words[:window_len])
            if subphrase in norm_original:
                return raw_quote
    return None


def _validated_draft(
    draft: CaseSummaryDraft,
    source_text: dict[UUID, str],
) -> CaseSummaryDraft:
    def validate_point(point: SummaryPoint) -> SummaryPoint | None:
        valid: list[SummaryCitation] = []
        seen: set[tuple[UUID, str]] = set()
        for citation in point.citations:
            target_unit_id = citation.source_unit_id
            original = source_text.get(target_unit_id)
            matched_quote = _find_evidence_quote(citation.evidence_quote, original) if original else None
            
            # If not found in the indicated unit, check other units in the current batch
            if not matched_quote:
                for alt_unit_id, alt_text in source_text.items():
                    if alt_unit_id != target_unit_id:
                        alt_match = _find_evidence_quote(citation.evidence_quote, alt_text)
                        if alt_match:
                            target_unit_id = alt_unit_id
                            matched_quote = alt_match
                            break

            if not matched_quote:
                continue

            key = (target_unit_id, matched_quote.casefold())
            if key not in seen:
                valid.append(SummaryCitation(source_unit_id=target_unit_id, evidence_quote=matched_quote))
                seen.add(key)

        if not valid:
            return None
        return point.model_copy(update={"citations": valid})

    narrative = [point for source in draft.narrative if (point := validate_point(source)) is not None]
    sections = []
    for section in draft.structured_sections:
        points = [point for source in section.points if (point := validate_point(source)) is not None]
        if points:
            sections.append(section.model_copy(update={"points": points}))
    return CaseSummaryDraft(narrative=narrative, structured_sections=sections)


def _render_point(point: SummaryPoint, source_info: dict[UUID, tuple[CaseDocument, DocumentTextUnit]]) -> dict:
    citations = []
    seen: set[tuple[UUID, str]] = set()
    for citation in point.citations:
        info = source_info.get(citation.source_unit_id)
        if info is None:
            continue
        document, unit = info
        key = (unit.id, citation.evidence_quote.casefold())
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "source_document_id": str(document.id),
                "source_filename": document.original_filename,
                "source_locator": unit.locator_label,
                "evidence_quote": citation.evidence_quote,
            }
        )
    return {"text": point.text, "citations": citations}


def process_case_summary(summary_run_id: UUID) -> None:
    """Generate both summary formats and persist only source-validated citations."""
    with SessionLocal() as db:
        run = db.get(CaseSummaryRun, summary_run_id)
        if run is None:
            return
        run.status = "processing"
        run.model = settings.gemini_model
        run.error_message = None
        db.commit()

        try:
            rows = db.execute(
                select(DocumentTextUnit, CaseDocument)
                .join(CaseDocument, DocumentTextUnit.document_id == CaseDocument.id)
                .where(CaseDocument.case_id == run.case_id, DocumentTextUnit.text != "")
                .order_by(CaseDocument.uploaded_at, DocumentTextUnit.unit_number)
            ).all()
            if not rows:
                raise ValueError("No extracted text was available for the case summary.")

            documents = list(dict.fromkeys(document.id for _, document in rows))
            document_refs = {document_id: f"doc_{index + 1}" for index, document_id in enumerate(documents)}
            source_info: dict[UUID, tuple[CaseDocument, DocumentTextUnit]] = {}
            source_text: dict[UUID, str] = {}
            sources: list[SourceText] = []
            for unit, document in rows:
                source_id = uuid4()
                source_info[source_id] = (document, unit)
                source_text[source_id] = unit.text
                sources.append(
                    SourceText(
                        source_unit_id=source_id,
                        document_name=document_refs[document.id],
                        locator="",
                        text=unit.text,
                    )
                )
            run.document_count = len(documents)
            run.text_unit_count = len(sources)
            db.commit()

            analyzer = GeminiCaseAnalyzer()
            drafts = [
                _validated_draft(analyzer.summarize_sources(batch), source_text)
                for batch in _source_batches(sources)
            ]
            while len(drafts) > 1:
                next_drafts = []
                for group in _draft_groups(drafts):
                    reduced = group[0] if len(group) == 1 else analyzer.synthesize_summary(group)
                    next_drafts.append(_validated_draft(reduced, source_text))
                if len(next_drafts) >= len(drafts):
                    raise ValueError("Summary synthesis could not reduce the source batches.")
                drafts = next_drafts

            final = drafts[0]
            narrative = [_render_point(point, source_info) for point in final.narrative]
            structured = [
                {
                    "section_key": section.section_key,
                    "title": section.title,
                    "points": [_render_point(point, source_info) for point in section.points],
                }
                for section in final.structured_sections
            ]
            run.narrative_summary = narrative
            run.structured_summary = structured
            run.point_count = len(narrative) + sum(len(section["points"]) for section in structured)
            if run.point_count == 0:
                raise ValueError("The model returned no summary points with verifiable source citations.")
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            case = db.get(Case, run.case_id)
            if case is not None:
                case.updated_at = datetime.now(UTC)
            db.commit()
        except Exception as error:  # noqa: BLE001 — don't store prompts, excerpts, or vendor response bodies.
            logger.error(
                "Case summary failed run_id=%s error_type=%s",
                summary_run_id,
                type(error).__name__,
            )
            db.rollback()
            failed = db.get(CaseSummaryRun, summary_run_id)
            if failed is None:
                return
            failed.status = "failed"
            failed.point_count = 0
            failed.narrative_summary = []
            failed.structured_summary = []
            failed.error_message = (
                "Summary generation did not complete. Check the Gemini API key, paid-project setting, model access, and connectivity, then retry."
            )
            failed.completed_at = datetime.now(UTC)
            db.commit()
