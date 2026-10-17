from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.config import settings
from app.core.encryption import EncryptedJSON, EncryptedText


class AdvocateAccount(Base):
    """The single advocate account created by first-run browser setup."""

    __tablename__ = "advocate_accounts"
    __table_args__ = (CheckConstraint("id = 1", name="ck_advocate_accounts_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    session_secret: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    client_reference: Mapped[str | None] = mapped_column(EncryptedText())
    court: Mapped[str | None] = mapped_column(EncryptedText())
    jurisdiction: Mapped[str | None] = mapped_column(EncryptedText())
    case_type: Mapped[str | None] = mapped_column(EncryptedText())
    stage: Mapped[str | None] = mapped_column(EncryptedText())
    case_number: Mapped[str | None] = mapped_column(EncryptedText())
    next_hearing_date: Mapped[date | None] = mapped_column(Date())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list["CaseDocument"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["CaseAnalysisRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    summary_runs: Mapped[list["CaseSummaryRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    knowledge_graph_runs: Mapped[list["CaseKnowledgeGraphRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    chat_conversations: Mapped[list["CaseChatConversation"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    deadlines: Mapped[list["CaseDeadline"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseDeadline.due_date"
    )


class CaseDocument(Base):
    __tablename__ = "case_documents"
    __table_args__ = (
        UniqueConstraint("case_id", "sha256", name="uq_case_documents_case_sha256"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(12), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    extraction_error: Mapped[str | None] = mapped_column(EncryptedText())
    description: Mapped[str | None] = mapped_column(EncryptedText())
    document_type: Mapped[str | None] = mapped_column(EncryptedText())
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="documents")
    text_units: Mapped[list["DocumentTextUnit"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentTextUnit.unit_number"
    )

    @property
    def text_unit_count(self) -> int:
        return len(self.text_units)

    @property
    def readable_location_count(self) -> int:
        return sum(bool(unit.text.strip()) for unit in self.text_units)

    @property
    def unreadable_location_count(self) -> int:
        return sum(not unit.text.strip() for unit in self.text_units)

    @property
    def page_count(self) -> int:
        return len({unit.page_number for unit in self.text_units if unit.page_number is not None})

    @property
    def pages_with_text_count(self) -> int:
        return len({unit.page_number for unit in self.text_units if unit.page_number is not None and unit.text.strip()})

    @property
    def pages_without_text_count(self) -> int:
        pages_with_text = {
            unit.page_number
            for unit in self.text_units
            if unit.page_number is not None and unit.text.strip()
        }
        all_pages = {unit.page_number for unit in self.text_units if unit.page_number is not None}
        return len(all_pages - pages_with_text)

    @property
    def review_location_count(self) -> int:
        return sum(unit.ocr_needs_review for unit in self.text_units)


class CaseDeadline(Base):
    __tablename__ = "case_deadlines"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    due_date: Mapped[date] = mapped_column(Date(), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(EncryptedText())
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="deadlines")


class DocumentTextUnit(Base):
    __tablename__ = "document_text_units"
    __table_args__ = (
        UniqueConstraint("document_id", "unit_number", name="uq_document_text_units_document_unit"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    locator_label: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[CaseDocument] = relationship(back_populates="text_units")

    @property
    def ocr_needs_review(self) -> bool:
        return (self.ocr_confidence is not None or "ocr" in self.extraction_method.casefold()) and (
            self.ocr_confidence is None
            or self.ocr_confidence < settings.ocr_review_confidence_threshold
        )


class CaseAnalysisRun(Base):
    __tablename__ = "case_analysis_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google_gemini")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    advocate_claims: Mapped[list[str]] = mapped_column(EncryptedJSON(), nullable=False, default=list)
    incomplete_sources_acknowledged: Mapped[bool] = mapped_column(nullable=False, default=False)
    retrieval_metadata: Mapped[dict | None] = mapped_column(EncryptedJSON())
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(EncryptedText())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="analysis_runs")

    facts: Mapped[list["CaseAnalysisFact"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    findings: Mapped[list["CaseAnalysisFinding"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    claim_reviews: Mapped[list["CaseClaimReview"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    knowledge_graph_runs: Mapped[list["CaseKnowledgeGraphRun"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )
    extraction_items: Mapped[list["CaseAnalysisExtractionItem"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )


class CaseAnalysisFact(Base):
    __tablename__ = "case_analysis_facts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_text_unit_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_text_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_key: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    statement: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    evidence_quote: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(EncryptedText())
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_start_char: Mapped[int | None] = mapped_column(Integer)
    source_end_char: Mapped[int | None] = mapped_column(Integer)

    analysis_run: Mapped[CaseAnalysisRun] = relationship(back_populates="facts")
    source_unit: Mapped[DocumentTextUnit] = relationship()
    findings_as_left: Mapped[list["CaseAnalysisFinding"]] = relationship(
        back_populates="left_fact", foreign_keys="CaseAnalysisFinding.left_fact_id"
    )
    findings_as_right: Mapped[list["CaseAnalysisFinding"]] = relationship(
        back_populates="right_fact", foreign_keys="CaseAnalysisFinding.right_fact_id"
    )

    @property
    def source_filename(self) -> str:
        return self.source_unit.document.original_filename

    @property
    def source_locator(self) -> str:
        return self.source_unit.locator_label

    @property
    def source_document_id(self) -> UUID:
        return self.source_unit.document_id

    @property
    def source_ocr_confidence(self) -> float | None:
        return self.source_unit.ocr_confidence

    @property
    def page_num(self) -> int | None:
        return self.source_unit.page_number

    @property
    def ocr_needs_review(self) -> bool:
        return (self.source_unit.ocr_confidence is not None or "ocr" in self.source_unit.extraction_method.casefold()) and (
            self.source_unit.ocr_confidence is None
            or self.source_unit.ocr_confidence < settings.ocr_review_confidence_threshold
        )

    @property
    def effective_confidence(self) -> float:
        if self.source_unit.ocr_confidence is None and "ocr" not in self.source_unit.extraction_method.casefold():
            return self.confidence
        ocr_factor = (self.source_unit.ocr_confidence or 0.0) / 100
        return self.confidence * max(0.0, min(1.0, ocr_factor))


class CaseAnalysisExtractionItem(Base):
    __tablename__ = "case_analysis_extraction_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_text_unit_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_text_units.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    text: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(EncryptedText())
    legal_role: Mapped[str | None] = mapped_column(EncryptedText())
    evidence_quote: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extractor: Mapped[str] = mapped_column(String(24), nullable=False)
    source_start_char: Mapped[int | None] = mapped_column(Integer)
    source_end_char: Mapped[int | None] = mapped_column(Integer)

    analysis_run: Mapped[CaseAnalysisRun] = relationship(back_populates="extraction_items")
    source_unit: Mapped[DocumentTextUnit] = relationship()

    @property
    def source_filename(self) -> str:
        return self.source_unit.document.original_filename

    @property
    def source_locator(self) -> str:
        return self.source_unit.locator_label

    @property
    def source_document_id(self) -> UUID:
        return self.source_unit.document_id

    @property
    def source_ocr_confidence(self) -> float | None:
        return self.source_unit.ocr_confidence

    @property
    def page_num(self) -> int | None:
        return self.source_unit.page_number

    @property
    def ocr_needs_review(self) -> bool:
        return (self.source_unit.ocr_confidence is not None or "ocr" in self.source_unit.extraction_method.casefold()) and (
            self.source_unit.ocr_confidence is None
            or self.source_unit.ocr_confidence < settings.ocr_review_confidence_threshold
        )


class CaseAnalysisFinding(Base):
    __tablename__ = "case_analysis_findings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_type: Mapped[str] = mapped_column(String(24), nullable=False)
    relation_label: Mapped[str | None] = mapped_column(EncryptedText())
    left_fact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=False
    )
    right_fact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=False
    )
    explanation: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="needs_review")
    review_note: Mapped[str | None] = mapped_column(EncryptedText())

    analysis_run: Mapped[CaseAnalysisRun] = relationship(back_populates="findings")
    left_fact: Mapped[CaseAnalysisFact] = relationship(
        back_populates="findings_as_left", foreign_keys=[left_fact_id]
    )
    right_fact: Mapped[CaseAnalysisFact] = relationship(
        back_populates="findings_as_right", foreign_keys=[right_fact_id]
    )


class CaseAnalysisReview(Base):
    __tablename__ = "case_analysis_reviews"
    __table_args__ = (UniqueConstraint("analysis_run_id", "target_kind", "target_id", name="uq_case_analysis_review_target"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    correction_text: Mapped[str | None] = mapped_column(EncryptedText())
    correction_category: Mapped[str | None] = mapped_column(EncryptedText())
    note: Mapped[str | None] = mapped_column(EncryptedText())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CaseClaimReview(Base):
    __tablename__ = "case_claim_reviews"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    claim_text: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    source_fact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=True
    )
    support_status: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    explanation: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    is_overstated: Mapped[bool] = mapped_column(nullable=False, default=False)
    overstatement_reason: Mapped[str | None] = mapped_column(EncryptedText())

    analysis_run: Mapped[CaseAnalysisRun] = relationship(back_populates="claim_reviews")
    source_fact: Mapped[CaseAnalysisFact | None] = relationship(foreign_keys=[source_fact_id])
    evidence: Mapped[list["CaseClaimReviewEvidence"]] = relationship(
        back_populates="claim_review", cascade="all, delete-orphan"
    )


class CaseClaimReviewEvidence(Base):
    __tablename__ = "case_claim_review_evidence"
    __table_args__ = (
        UniqueConstraint("claim_review_id", "evidence_fact_id", name="uq_claim_review_evidence_pair"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    claim_review_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_claim_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_fact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_facts.id", ondelete="CASCADE"), nullable=False
    )

    claim_review: Mapped[CaseClaimReview] = relationship(back_populates="evidence")
    evidence_fact: Mapped[CaseAnalysisFact] = relationship(foreign_keys=[evidence_fact_id])


class CaseSummaryRun(Base):
    __tablename__ = "case_summary_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google_gemini")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incomplete_sources_acknowledged: Mapped[bool] = mapped_column(nullable=False, default=False)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    narrative_summary: Mapped[list[dict]] = mapped_column(EncryptedJSON(), nullable=False, default=list)
    structured_summary: Mapped[list[dict]] = mapped_column(EncryptedJSON(), nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(EncryptedText())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="summary_runs")


class CaseKnowledgeGraphRun(Base):
    __tablename__ = "case_knowledge_graph_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="neo4j")
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_snapshot: Mapped[dict | None] = mapped_column(EncryptedJSON())
    error_message: Mapped[str | None] = mapped_column(EncryptedText())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="knowledge_graph_runs")
    analysis_run: Mapped[CaseAnalysisRun] = relationship(back_populates="knowledge_graph_runs")


class CaseChatConversation(Base):
    __tablename__ = "case_chat_conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    case: Mapped[Case] = relationship(back_populates="chat_conversations")
    messages: Mapped[list["CaseChatMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="CaseChatMessage.created_at"
    )


class CaseChatMessage(Base):
    __tablename__ = "case_chat_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("case_chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    citations: Mapped[list[dict] | None] = mapped_column(EncryptedJSON())
    follow_up_questions: Mapped[list[str]] = mapped_column(EncryptedJSON(), nullable=False, default=list)
    retrieval_mode: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[CaseChatConversation] = relationship(back_populates="messages")


class CaseAuthorityReview(Base):
    __tablename__ = "case_authority_reviews"
    __table_args__ = (UniqueConstraint("case_id", "provider", "source_id", name="uq_case_authority_review_source"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    url: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="needs_review")
    note: Mapped[str | None] = mapped_column(EncryptedText())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"

    jti_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
