from types import SimpleNamespace
from uuid import uuid4

from app.services import knowledge_graph_processing as graph
from app.services.gemini_analysis import (
    ClassifiedGraphRelation,
    GraphRelationBatch,
    GraphRelationCandidate,
)


def _unit(document_id=None, unit_number=1):
    document_id = document_id or uuid4()
    document = SimpleNamespace(id=document_id, original_filename="affidavit.pdf")
    return SimpleNamespace(
        id=uuid4(),
        document_id=document_id,
        document=document,
        unit_number=unit_number,
        page_number=unit_number,
        locator_label=f"Page {unit_number}",
        ocr_confidence=99.0,
        ocr_needs_review=False,
    )


def test_graph_nodes_include_source_evidence_parties_provisions_and_rule_link() -> None:
    case_id, graph_run_id = uuid4(), uuid4()
    unit = _unit()
    fact_id = uuid4()
    fact = SimpleNamespace(
        id=fact_id,
        source_unit=unit,
        fact_type="date",
        topic_key="notice date",
        statement="Notice was served on 5 January.",
        evidence_quote="Notice served on 5 January.",
        effective_confidence=0.92,
        source_start_char=10,
        source_end_char=38,
    )
    issue = SimpleNamespace(
        id=uuid4(), source_unit=unit, item_kind="sentence", category="issue",
        text="Whether Section 12 applied to the notice?", evidence_quote="Whether Section 12 applied to the notice?",
        confidence=0.88, source_start_char=40, source_end_char=82,
    )
    provision = SimpleNamespace(
        id=uuid4(), source_unit=unit, item_kind="legal_reference", category="section",
        text="Section 12", normalized_value="Section 12", evidence_quote="Section 12",
        confidence=0.95, source_start_char=49, source_end_char=59,
    )
    party = SimpleNamespace(
        id=uuid4(), source_unit=unit, item_kind="entity", category="person",
        text="A. Rao", normalized_value="A. Rao", legal_role="petitioner", evidence_quote="Petitioner A. Rao",
        confidence=0.9, source_start_char=0, source_end_char=6,
    )
    analysis = SimpleNamespace(
        facts=[fact], extraction_items=[issue, provision, party], findings=[],
    )

    nodes, edges = graph._make_graph(case_id, graph_run_id, analysis)
    kinds = {node["node_type"] for node in nodes}
    assert {"fact", "issue", "provision", "party", "evidence"} <= kinds
    assert all(node["source_filename"] == "affidavit.pdf" for node in nodes)
    assert any(edge["relation"] == "applies_to" and edge["source_kind"] == "rule_heuristic" for edge in edges)


def test_candidate_retrieval_is_rule_bounded_and_gemini_labels_only_selected_pairs(monkeypatch) -> None:
    case_id, graph_run_id = uuid4(), uuid4()
    document_id = str(uuid4())
    fact = {
        "node_id": "fact-1", "node_type": "fact", "text": "The notice was served on 5 January.",
        "source_document_id": document_id, "unit_number": 4, "evidence_quote": "Notice served on 5 January.",
        "source_filename": "affidavit.pdf",
    }
    issue = {
        "node_id": "issue-1", "node_type": "issue", "text": "Whether the notice was served on 5 January?",
        "source_document_id": document_id, "unit_number": 4, "evidence_quote": "Whether notice was served?",
        "source_filename": "affidavit.pdf",
    }
    candidates = graph._relation_candidates(case_id, graph_run_id, [fact, issue])
    assert len(candidates) == 1
    assert candidates[0].left_node_id == "fact-1"
    assert candidates[0].right_node_id == "issue-1"

    class FakeAnalyzer:
        def classify_graph_relations(self, batch):
            return GraphRelationBatch(relations=[
                ClassifiedGraphRelation(
                    pair_id=batch[0].pair_id,
                    relation="supports",
                    explanation="The fact directly answers the issue's disputed date.",
                    confidence=0.81,
                )
            ])

    monkeypatch.setattr(graph, "GeminiCaseAnalyzer", FakeAnalyzer)
    edges = graph._classify_candidates(case_id, graph_run_id, candidates)
    assert len(edges) == 1
    assert edges[0]["relation"] == "supports"
    assert edges[0]["source_kind"] == "llm_relation_classification"


def test_hybrid_graph_search_ranks_semantic_match_and_lexical_overlap(monkeypatch) -> None:
    class FakeEmbeddingModel:
        def encode(self, *_args, **_kwargs):
            return [[1.0, 0.0]]

    monkeypatch.setattr(graph, "_embedding_model", lambda: FakeEmbeddingModel())
    nodes = [
        {
            "node_id": "semantic", "node_type": "fact", "label": "notice date",
            "text": "Notice delivered on a particular date.", "evidence_quote": "",
            "embedding": [1.0, 0.0],
        },
        {
            "node_id": "lexical", "node_type": "fact", "label": "notice delivery",
            "text": "Notice delivered to the respondent.", "evidence_quote": "notice delivery",
            "embedding": [0.0, 1.0],
        },
    ]

    scored = graph._hybrid_graph_scores("notice delivery", nodes)

    assert scored[0][3]["node_id"] == "semantic"
    assert scored[0][1] == 1.0
    assert scored[0][2] == 0.5
    assert scored[1][3]["node_id"] == "lexical"
