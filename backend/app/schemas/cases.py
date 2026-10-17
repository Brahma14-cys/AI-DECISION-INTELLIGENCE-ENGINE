from datetime import datetime
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    client_reference: str | None = Field(default=None, max_length=120)
    court: str | None = Field(default=None, max_length=160)
    jurisdiction: str | None = Field(default=None, max_length=120)
    case_type: str | None = Field(default=None, max_length=120)
    stage: str | None = Field(default=None, max_length=120)
    case_number: str | None = Field(default=None, max_length=120)
    next_hearing_date: date | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Case name cannot be empty.")
        return normalized


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    client_reference: str | None = Field(default=None, max_length=120)
    court: str | None = Field(default=None, max_length=160)
    jurisdiction: str | None = Field(default=None, max_length=120)
    case_type: str | None = Field(default=None, max_length=120)
    stage: str | None = Field(default=None, max_length=120)
    case_number: str | None = Field(default=None, max_length=120)
    next_hearing_date: date | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("Case name cannot be empty.")
            return normalized
        return value

    @field_validator("client_reference", "court", "jurisdiction", "case_type", "stage", "case_number", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_patch(self) -> "CaseUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one case field to update.")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Case name cannot be cleared.")
        return self


class CaseDocumentUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2_000)
    document_type: str | None = Field(default=None, max_length=120)

    @field_validator("description", "document_type", mode="before")
    @classmethod
    def normalize_document_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> "CaseDocumentUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide a document description or type to update.")
        return self


class FindingReviewUpdate(BaseModel):
    review_status: Literal["confirmed_contradiction", "possible_contradiction", "not_a_contradiction", "needs_review"]
    review_note: str | None = Field(default=None, max_length=2_000)

    @field_validator("review_note", mode="before")
    @classmethod
    def normalize_review_note(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class AnalysisReviewUpdate(BaseModel):
    target_kind: Literal["fact", "extraction_item", "finding", "claim_review"]
    target_id: UUID
    status: str = Field(min_length=2, max_length=32)
    correction_text: str | None = Field(default=None, max_length=8_000)
    correction_category: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("status", "correction_text", "correction_category", "note", mode="before")
    @classmethod
    def clean_review_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    client_reference: str | None
    court: str | None
    jurisdiction: str | None
    case_type: str | None
    stage: str | None
    case_number: str | None = None
    next_hearing_date: date | None = None
    analysis_status: str | None = None
    attention_count: int = 0
    deadline_attention_count: int = 0
    created_at: datetime
    updated_at: datetime


class CaseDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    original_filename: str
    content_type: str
    file_extension: str
    size_bytes: int
    sha256: str
    processing_status: str
    extraction_error: str | None
    description: str | None = None
    document_type: str | None = None
    text_unit_count: int = 0
    readable_location_count: int = 0
    unreadable_location_count: int = 0
    page_count: int = 0
    pages_with_text_count: int = 0
    pages_without_text_count: int = 0
    review_location_count: int = 0
    near_duplicate_matches: list["CaseDocumentSimilarityRead"] = Field(default_factory=list)
    uploaded_at: datetime


class CaseDocumentSimilarityRead(BaseModel):
    document_id: UUID
    filename: str
    similarity: float = Field(ge=0.82, le=1.0)


class CaseDeadlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    due_date: date
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("title", "note", mode="before")
    @classmethod
    def normalize_deadline_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("Enter a deadline or event name.")
        return value


class CaseDeadlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=2_000)
    status: Literal["open", "complete"] | None = None

    @field_validator("title", "note", mode="before")
    @classmethod
    def normalize_deadline_text(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_change(self) -> "CaseDeadlineUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide a deadline field to update.")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Deadline name cannot be cleared.")
        return self


class CaseDeadlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    title: str
    due_date: date
    note: str | None
    status: Literal["open", "complete"]
    created_at: datetime


class DocumentTextUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    unit_number: int
    page_number: int | None
    locator_label: str
    text: str
    character_count: int
    extraction_method: str
    ocr_confidence: float | None
    ocr_needs_review: bool
    created_at: datetime


class UploadRejection(BaseModel):
    filename: str
    reason: str


class UploadBatchResult(BaseModel):
    uploaded: list[CaseDocumentRead]
    rejected: list[UploadRejection]


class CaseAnalysisAvailability(BaseModel):
    ready: bool
    provider: str = "google_gemini"
    model: str
    message: str


class CaseAnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    status: str
    provider: str
    model: str
    retrieval_metadata: dict[str, Any] | None = None
    document_count: int
    text_unit_count: int
    incomplete_sources_acknowledged: bool = False
    fact_count: int
    finding_count: int
    claim_review_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CaseAnalysisFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fact_type: str
    topic_key: str
    statement: str
    evidence_quote: str
    normalized_value: str | None
    confidence: float
    effective_confidence: float
    source_ocr_confidence: float | None
    ocr_needs_review: bool
    source_text_unit_id: UUID
    source_document_id: UUID
    source_filename: str
    source_locator: str
    page_num: int | None
    source_start_char: int | None
    source_end_char: int | None


class CaseAnalysisExtractionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_kind: str
    category: str
    text: str
    normalized_value: str | None
    legal_role: str | None
    evidence_quote: str
    confidence: float
    source_ocr_confidence: float | None
    ocr_needs_review: bool
    extractor: str
    source_text_unit_id: UUID
    source_document_id: UUID
    source_filename: str
    source_locator: str
    page_num: int | None
    source_start_char: int | None
    source_end_char: int | None


class CaseAnalysisFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_type: str
    relation_label: str | None
    explanation: str
    confidence: float
    review_status: str = "needs_review"
    review_note: str | None = None
    left_fact: CaseAnalysisFactRead
    right_fact: CaseAnalysisFactRead


class CaseAnalysisStartRequest(BaseModel):
    advocate_claims: list[str] = Field(default_factory=list, max_length=20)
    acknowledge_incomplete_sources: bool = False

    @field_validator("advocate_claims")
    @classmethod
    def validate_claims(cls, claims: list[str]) -> list[str]:
        cleaned = [claim.strip() for claim in claims]
        if any(len(claim) < 3 or len(claim) > 2_000 for claim in cleaned):
            raise ValueError("Each claim must contain between 3 and 2,000 characters.")
        if len({claim.casefold() for claim in cleaned}) != len(cleaned):
            raise ValueError("Remove duplicate claims before analysis.")
        return cleaned


class CaseClaimReviewEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_fact: CaseAnalysisFactRead


class CaseClaimReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_kind: str
    claim_text: str
    support_status: str
    explanation: str
    is_overstated: bool
    overstatement_reason: str | None
    source_fact: CaseAnalysisFactRead | None
    evidence: list[CaseClaimReviewEvidenceRead]


class CaseAnalysisReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_kind: str
    target_id: UUID
    status: str
    correction_text: str | None
    correction_category: str | None
    note: str | None
    created_at: datetime


class CaseAnalysisRead(BaseModel):
    run: CaseAnalysisRunRead
    facts: list[CaseAnalysisFactRead]
    extraction_items: list[CaseAnalysisExtractionItemRead] = Field(default_factory=list)
    findings: list[CaseAnalysisFindingRead]
    claim_reviews: list[CaseClaimReviewRead]
    advocate_reviews: list[CaseAnalysisReviewRead] = Field(default_factory=list)


class CaseSummaryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    status: str
    provider: str
    model: str
    document_count: int
    text_unit_count: int
    incomplete_sources_acknowledged: bool = False
    point_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CaseSummaryCitationRead(BaseModel):
    source_document_id: UUID
    source_filename: str
    source_locator: str
    evidence_quote: str


class CaseSummaryPointRead(BaseModel):
    text: str
    citations: list[CaseSummaryCitationRead]


class CaseSummarySectionRead(BaseModel):
    section_key: str
    title: str
    points: list[CaseSummaryPointRead]


class CaseSummaryRead(BaseModel):
    run: CaseSummaryRunRead
    narrative_summary: list[CaseSummaryPointRead]
    structured_summary: list[CaseSummarySectionRead]


class CaseSummaryStartRequest(BaseModel):
    acknowledge_incomplete_sources: bool = False


class CaseKnowledgeGraphRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    analysis_run_id: UUID
    status: str
    provider: str
    embedding_model: str
    node_count: int
    edge_count: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CaseKnowledgeGraphNodeRead(BaseModel):
    node_id: str
    node_type: str
    text: str
    label: str
    category: str
    evidence_quote: str
    confidence: float
    source_document_id: UUID
    source_filename: str
    source_text_unit_id: UUID
    source_locator: str
    page_num: int | None
    source_start_char: int | None = None
    source_end_char: int | None = None
    ocr_confidence: float | None = None
    ocr_needs_review: bool = False


class CaseKnowledgeGraphEdgeRead(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    explanation: str
    confidence: float
    source_kind: str


class CaseKnowledgeGraphRead(BaseModel):
    run: CaseKnowledgeGraphRunRead
    nodes: list[CaseKnowledgeGraphNodeRead] = Field(default_factory=list)
    edges: list[CaseKnowledgeGraphEdgeRead] = Field(default_factory=list)
    capabilities: dict[str, str] = Field(default_factory=dict)


class CaseKnowledgeGraphSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2_000)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Search query must contain at least two non-space characters.")
        return normalized


class CaseKnowledgeGraphSearchContext(BaseModel):
    relation: str
    explanation: str
    confidence: float
    source_kind: str
    source_node_id: str
    related_node: CaseKnowledgeGraphNodeRead


class CaseKnowledgeGraphSearchHit(BaseModel):
    node: CaseKnowledgeGraphNodeRead
    score: float
    semantic_score: float
    lexical_score: float
    related_context: list[CaseKnowledgeGraphSearchContext] = Field(default_factory=list)


class CaseKnowledgeGraphSearchRead(BaseModel):
    case_id: UUID
    graph_run_id: UUID
    query: str
    results: list[CaseKnowledgeGraphSearchHit] = Field(default_factory=list)
    search_truncated: bool = False
