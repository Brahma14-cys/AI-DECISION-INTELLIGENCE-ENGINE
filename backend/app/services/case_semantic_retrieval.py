"""Ephemeral semantic fact retrieval for a single analysis run."""

from collections import defaultdict
from uuid import UUID

import numpy as np

from app.db.models import CaseAnalysisFact


MAX_SEMANTIC_FACTS_PER_RUN = 800
MAX_SEMANTIC_NEIGHBORS_PER_FACT = 8
SEMANTIC_SIMILARITY_THRESHOLD = 0.72
_FLEXIBLE_FACT_TYPES = {"event", "claim", "other"}


def select_embedding_facts(facts: list[CaseAnalysisFact]) -> list[CaseAnalysisFact]:
    """Select confidence-ranked facts in document-round-robin order under a cap."""
    by_document: dict[UUID, list[CaseAnalysisFact]] = defaultdict(list)
    for fact in facts:
        by_document[fact.source_unit.document_id].append(fact)
    for document_facts in by_document.values():
        document_facts.sort(key=lambda item: item.effective_confidence, reverse=True)

    selected: list[CaseAnalysisFact] = []
    depth = max((len(items) for items in by_document.values()), default=0)
    for index in range(depth):
        for document_facts in by_document.values():
            if index < len(document_facts):
                selected.append(document_facts[index])
                if len(selected) >= MAX_SEMANTIC_FACTS_PER_RUN:
                    return selected
    return selected


def semantic_candidate_pairs(
    facts: list[CaseAnalysisFact],
    vectors: list[list[float]],
    *,
    similarity_threshold: float = SEMANTIC_SIMILARITY_THRESHOLD,
    neighbors_per_fact: int = MAX_SEMANTIC_NEIGHBORS_PER_FACT,
) -> list[tuple[CaseAnalysisFact, CaseAnalysisFact]]:
    """Return bounded, high-similarity cross-document candidate pairs.

    Embeddings exist only in memory for this call. They are neither stored in the
    database nor used as findings; Gemini still adjudicates each returned pair.
    """
    if len(facts) != len(vectors) or len(facts) < 2:
        return []
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        return []
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        return []
    matrix = matrix / norms
    similarities = matrix @ matrix.T
    by_id = {fact.id: fact for fact in facts}
    selected: set[tuple[UUID, UUID]] = set()

    for index, fact in enumerate(facts):
        compatible: list[tuple[float, CaseAnalysisFact]] = []
        for peer_index, score in enumerate(similarities[index]):
            if peer_index == index:
                continue
            peer = facts[peer_index]
            if peer.source_unit.document_id == fact.source_unit.document_id:
                continue
            if (
                fact.fact_type != peer.fact_type
                and fact.fact_type not in _FLEXIBLE_FACT_TYPES
                and peer.fact_type not in _FLEXIBLE_FACT_TYPES
            ):
                continue
            if float(score) < similarity_threshold:
                continue
            compatible.append((float(score), peer))
        for _, peer in sorted(compatible, key=lambda item: item[0], reverse=True)[:neighbors_per_fact]:
            selected.add(tuple(sorted((fact.id, peer.id), key=str)))

    return [(by_id[left], by_id[right]) for left, right in sorted(selected, key=lambda item: (str(item[0]), str(item[1])))]
