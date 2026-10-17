from uuid import uuid4

from app.services.gemini_analysis import SourceText, StructuredExtractionItem
from app.services.sentence_role_classifier import MODEL_LABELS, classify_sentence_roles


def test_trained_role_item_uses_a_separate_kind_from_gemini_sentence_classes() -> None:
    item = StructuredExtractionItem(
        source_unit_id=uuid4(),
        item_kind="sentence_role",
        category="ratio_decidendi",
        text="The statute requires notice.",
        evidence_quote="The statute requires notice.",
        confidence=0.73,
        extractor="inlegalbert",
    )

    assert item.item_kind == "sentence_role"
    assert item.category == "ratio_decidendi"
    assert item.extractor == "inlegalbert"


def test_role_taxonomy_matches_the_seven_labeled_corpus_roles() -> None:
    assert MODEL_LABELS == {
        "argument",
        "fact",
        "precedent",
        "ratio_decidendi",
        "ruling_lower_court",
        "ruling_present_court",
        "statute",
    }


def test_classifier_fails_open_when_the_optional_local_model_is_unavailable(monkeypatch) -> None:
    from app.services import sentence_role_classifier

    monkeypatch.setattr(sentence_role_classifier, "_load_classifier", lambda: None)
    source = SourceText(
        source_unit_id=uuid4(),
        document_name="judgment.pdf",
        locator="Page 1",
        text="The court considered the evidence.",
    )

    assert classify_sentence_roles([source]) == []
