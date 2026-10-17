from uuid import uuid4

from app.services.gemini_analysis import SourceText
from app.services.legal_extraction_rules import extract_rule_based_indicators


def test_rule_extraction_normalizes_indian_legal_dates_amounts_and_references() -> None:
    source_id = uuid4()
    source = SourceText(
        source_unit_id=source_id,
        document_name="notice.pdf",
        locator="Page 2",
        text=(
            "The notice was served on 12 March 2024. The cheque amount was Rs. 50,000/-. "
            "The complaint invokes Section 138 of the Negotiable Instruments Act. "
            "See 2024 3 SCC 120."
        ),
    )

    items = extract_rule_based_indicators(source)

    assert any(item.item_kind == "date" and item.normalized_value == "2024-03-12" for item in items)
    assert any(item.item_kind == "amount" and item.normalized_value == "INR 50000.00" for item in items)
    assert any(item.item_kind == "legal_reference" and item.category == "section_or_rule" for item in items)
    assert any(item.item_kind == "legal_reference" and item.category == "case_citation" for item in items)
    assert all(item.source_unit_id == source_id and item.extractor == "regex" for item in items)
    assert all(item.evidence_quote in source.text for item in items)


def test_rule_extraction_ignores_ambiguous_invalid_dates() -> None:
    source = SourceText(
        source_unit_id=uuid4(),
        document_name="order.pdf",
        locator="Page 1",
        text="A date is written as 39 March 2024 and should not normalize.",
    )

    assert not [item for item in extract_rule_based_indicators(source) if item.item_kind == "date"]


def test_rule_extraction_preserves_repeated_reference_mentions() -> None:
    source = SourceText(
        source_unit_id=uuid4(),
        document_name="petition.pdf",
        locator="Page 1",
        text="Section 138 applies. Section 138 is also mentioned later.",
    )

    references = [
        item for item in extract_rule_based_indicators(source)
        if item.item_kind == "legal_reference" and item.category == "section_or_rule"
    ]

    assert [item.text for item in references] == ["Section 138", "Section 138"]
