"""Deterministic English/Indian-legal extraction backstops for Module 2."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from app.services.gemini_analysis import SourceText, StructuredExtractionItem


_MONTH = (
    r"January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_DATE_PATTERNS = (
    re.compile(rf"\b(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+(?:{_MONTH})\.?[,]?\s+(?:19|20)\d{{2}}\b", re.IGNORECASE),
    re.compile(rf"\b(?:{_MONTH})\.?\s+(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[,]?\s+(?:19|20)\d{{2}}\b", re.IGNORECASE),
    re.compile(r"\b(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2}\b"),
)
_AMOUNT = re.compile(
    r"(?<![A-Za-z0-9])(?P<currency>₹|INR\b|Rs\.?(?=\s)|Rupees\b)\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d{1,2})?)(?:\s*/-)?",
    re.IGNORECASE,
)
_SECTION = re.compile(
    r"\b(?P<kind>section|sec\.?|article|art\.?|rule|order)\s+"
    r"(?P<number>\d+[A-Za-z]?(?:\s*\([^)]{1,20}\))?)"
    r"(?:\s+(?:of|under)\s+(?:the\s+)?"
    r"(?P<law>(?:[A-Za-z][A-Za-z&.,'-]*\s+){0,8}(?:Act|Code|Rules|Constitution)))?",
    re.IGNORECASE,
)
_CASE_CITATION = re.compile(
    r"\b(?:AIR\s+(?:19|20)\d{2}\s+[A-Z]{2,8}\s+\d+|"
    r"(?:19|20)\d{2}\s+\d+\s+SCC\s+\d+|"
    r"(?:19|20)\d{2}\s+SCC\s+OnLine\s+[A-Z]{2,8}\s+\d+|"
    r"\[(?:19|20)\d{2}\]\s+INSC\s+\d+)\b",
    re.IGNORECASE,
)
_ACT_NAMES = re.compile(
    r"\b(?:Constitution of India|Code of Civil Procedure|Code of Criminal Procedure|"
    r"Bharatiya Nyaya Sanhita|Bharatiya Nagarik Suraksha Sanhita|Bharatiya Sakshya Adhiniyam|"
    r"Indian Penal Code|Indian Evidence Act|Negotiable Instruments Act|Companies Act|"
    r"Specific Relief Act|Transfer of Property Act|Limitation Act|Arbitration and Conciliation Act)"
    r"(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)


def _normalize_date(value: str) -> str | None:
    clean = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean.replace(",", " ")).strip().replace("  ", " ")
    formats = (
        "%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    )
    for date_format in formats:
        try:
            return datetime.strptime(clean, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def extract_rule_based_indicators(source: SourceText) -> list[StructuredExtractionItem]:
    """Extract exact date, amount, and legal-reference spans without model inference."""
    text = source.text
    items: list[StructuredExtractionItem] = []

    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            normalized = _normalize_date(value)
            if normalized:
                items.append(
                    StructuredExtractionItem(
                        source_unit_id=source.source_unit_id,
                        item_kind="date",
                        category="date_mention",
                        text=value,
                        normalized_value=normalized,
                        evidence_quote=value,
                        confidence=1.0,
                        extractor="regex",
                    )
                )

    for match in _AMOUNT.finditer(text):
        value = match.group(0).strip()
        try:
            numeric = Decimal(match.group("amount").replace(",", ""))
        except InvalidOperation:
            continue
        currency = "INR" if match.group("currency").casefold() in {"₹", "inr", "rs", "rs.", "rupees"} else match.group("currency").upper()
        items.append(
            StructuredExtractionItem(
                source_unit_id=source.source_unit_id,
                item_kind="amount",
                category="currency_amount",
                text=value,
                normalized_value=f"{currency} {numeric:.2f}",
                evidence_quote=value,
                confidence=1.0,
                extractor="regex",
            )
        )

    for pattern, category in (
        (_CASE_CITATION, "case_citation"),
        (_SECTION, "section_or_rule"),
        (_ACT_NAMES, "statute_or_code"),
    ):
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            items.append(
                StructuredExtractionItem(
                    source_unit_id=source.source_unit_id,
                    item_kind="legal_reference",
                    category=category,
                    text=value,
                    normalized_value=" ".join(value.split()),
                    evidence_quote=value,
                    confidence=1.0,
                    extractor="regex",
                )
            )

    return items
