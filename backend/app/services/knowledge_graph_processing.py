"""Build a source-grounded case graph from a completed Module 2 analysis."""

from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.db.models import (
    Case,
    CaseAnalysisExtractionItem,
    CaseAnalysisFact,
    CaseAnalysisFinding,
    CaseAnalysisRun,
    CaseKnowledgeGraphRun,
    DocumentTextUnit,
)
from app.services.case_analysis_processing import gemini_is_ready
from app.services.gemini_analysis import (
    GeminiCaseAnalyzer,
    GraphRelationCandidate,
)


MAX_GRAPH_RELATION_CANDIDATES = 100
GRAPH_RELATION_BATCH_SIZE = 25
GRAPH_NODE_WRITE_BATCH_SIZE = 250
MAX_GRAPH_SEARCH_NODES = 15_000
MAX_GRAPH_CONTEXT_EDGES = 240
logger = logging.getLogger(__name__)
PARTY_ROLES = {
    "petitioner", "respondent", "appellant", "plaintiff", "defendant",
    "complainant", "accused", "claimant", "applicant", "opposite party",
}
STOP_WORDS = {
    "about", "after", "against", "among", "also", "been", "being", "between",
    "case", "court", "from", "have", "into", "issue", "legal", "matter", "more",
    "other", "over", "same", "should", "that", "their", "there", "these", "they",
    "this", "those", "under", "upon", "were", "what", "when", "where", "which",
    "while", "with", "would",
}


def graph_is_configured() -> bool:
    return bool(
        settings.knowledge_graph_enabled
        and settings.neo4j_uri
        and settings.neo4j_user
        and settings.neo4j_password
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _source_data(unit: DocumentTextUnit) -> dict:
    document = unit.document
    return {
        "source_document_id": str(document.id),
        "source_filename": document.original_filename,
        "source_text_unit_id": str(unit.id),
        "source_locator": unit.locator_label,
        "page_num": unit.page_number,
        "unit_number": unit.unit_number,
        "ocr_confidence": unit.ocr_confidence,
        "ocr_needs_review": unit.ocr_needs_review,
    }


def _node(
    case_id: UUID,
    graph_run_id: UUID,
    node_type: str,
    text: str,
    label: str,
    category: str,
    source: dict,
    evidence_quote: str,
    confidence: float,
    node_key: str,
    source_start_char: int | None = None,
    source_end_char: int | None = None,
) -> dict:
    return {
        "node_id": f"{graph_run_id}:{node_type}:{_stable_id(str(case_id), node_key)[:32]}",
        "case_id": str(case_id),
        "graph_run_id": str(graph_run_id),
        "node_type": node_type,
        "text": text[:8_000],
        "label": label[:300],
        "category": category[:64],
        "evidence_quote": evidence_quote[:8_000],
        "confidence": float(confidence),
        "source_start_char": source_start_char,
        "source_end_char": source_end_char,
        **source,
    }


def _add_evidence_node(
    case_id: UUID,
    graph_run_id: UUID,
    source: dict,
    quote: str,
    confidence: float,
    nodes: dict[str, dict],
    edges: list[dict],
    target_node_id: str,
) -> None:
    if not quote.strip():
        return
    key = f"{source['source_text_unit_id']}:{quote.casefold()}"
    evidence = _node(
        case_id,
        graph_run_id,
        "evidence",
        quote,
        "Evidence passage",
        "source_quote",
        source,
        quote,
        confidence,
        key,
    )
    nodes.setdefault(evidence["node_id"], evidence)
    edges.append(
        _edge(
            case_id,
            graph_run_id,
            evidence["node_id"],
            target_node_id,
            "supports",
            "Source passage attached to the extracted item; review it in its original document context.",
            confidence,
            "source_evidence",
        )
    )


def _edge(
    case_id: UUID,
    graph_run_id: UUID,
    source_id: str,
    target_id: str,
    relation: str,
    explanation: str,
    confidence: float,
    source_kind: str,
) -> dict:
    edge_id = _stable_id(str(graph_run_id), source_id, relation, target_id)
    return {
        "edge_id": edge_id,
        "case_id": str(case_id),
        "graph_run_id": str(graph_run_id),
        "source_id": source_id,
        "target_id": target_id,
        "relation": relation,
        "explanation": explanation[:1_000],
        "confidence": float(confidence),
        "source_kind": source_kind,
    }


def _make_graph(
    case_id: UUID,
    graph_run_id: UUID,
    analysis_run: CaseAnalysisRun,
) -> tuple[list[dict], list[dict]]:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    fact_ids: dict[UUID, str] = {}
    issue_nodes: list[dict] = []
    provision_nodes: list[dict] = []
    entity_nodes: dict[str, dict] = {}

    for fact in analysis_run.facts:
        source = _source_data(fact.source_unit)
        fact_node = _node(
            case_id, graph_run_id, "fact", fact.statement, fact.topic_key,
            fact.fact_type, source, fact.evidence_quote, fact.effective_confidence,
            str(fact.id), fact.source_start_char, fact.source_end_char,
        )
        nodes[fact_node["node_id"]] = fact_node
        fact_ids[fact.id] = fact_node["node_id"]
        _add_evidence_node(
            case_id, graph_run_id, source, fact.evidence_quote,
            fact.effective_confidence, nodes, edges, fact_node["node_id"],
        )

    for item in analysis_run.extraction_items:
        source = _source_data(item.source_unit)
        if item.item_kind == "sentence" and item.category == "issue":
            graph_node = _node(
                case_id, graph_run_id, "issue", item.text, "Case issue", item.category,
                source, item.evidence_quote, item.confidence, str(item.id),
                item.source_start_char, item.source_end_char,
            )
            nodes[graph_node["node_id"]] = graph_node
            issue_nodes.append(graph_node)
        elif item.item_kind == "legal_reference":
            graph_node = _node(
                case_id, graph_run_id, "provision", item.text, item.normalized_value or item.text,
                item.category, source, item.evidence_quote, item.confidence, str(item.id),
                item.source_start_char, item.source_end_char,
            )
            nodes[graph_node["node_id"]] = graph_node
            provision_nodes.append(graph_node)
        elif item.item_kind == "entity" and item.category in {"person", "organization"}:
            role = (item.legal_role or "").strip().casefold()
            if role not in PARTY_ROLES:
                continue
            canonical = (item.normalized_value or item.text).strip()
            node_key = f"{item.category}:{canonical.casefold()}"
            graph_node = entity_nodes.get(node_key)
            if graph_node is None:
                graph_node = _node(
                    case_id, graph_run_id, "party", canonical, canonical,
                    role, source, item.evidence_quote, item.confidence, node_key,
                    item.source_start_char, item.source_end_char,
                )
                entity_nodes[node_key] = graph_node
                nodes[graph_node["node_id"]] = graph_node
            _add_evidence_node(
                case_id, graph_run_id, source, item.evidence_quote, item.confidence,
                nodes, edges, graph_node["node_id"],
            )

    for issue in issue_nodes + provision_nodes:
        _add_evidence_node(
            case_id, graph_run_id,
            {key: issue[key] for key in (
                "source_document_id", "source_filename", "source_text_unit_id", "source_locator",
                "page_num", "unit_number", "ocr_confidence", "ocr_needs_review",
            )},
            issue["evidence_quote"], issue["confidence"], nodes, edges, issue["node_id"],
        )

    for issue in issue_nodes:
        issue_text = f"{issue['text']} {issue['evidence_quote']}".casefold()
        for provision in provision_nodes:
            provision_text = provision["text"].strip().casefold()
            normalized = provision["label"].strip().casefold()
            cited_text = next(
                (value for value in (normalized, provision_text) if len(value) >= 4 and value in issue_text),
                None,
            )
            if cited_text:
                edges.append(
                    _edge(
                        case_id, graph_run_id, provision["node_id"], issue["node_id"],
                        "applies_to",
                        "Rule match: the extracted provision text also appears in the issue passage. "
                        "This is a candidate link only; it does not establish legal applicability.",
                        0.65,
                        "rule_heuristic",
                    )
                )

    for finding in analysis_run.findings:
        left = fact_ids.get(finding.left_fact_id)
        right = fact_ids.get(finding.right_fact_id)
        if not left or not right:
            continue
        relation = "contradicts" if finding.finding_type == "contradiction" else None
        if finding.finding_type == "relation" and finding.relation_label in {"supports", "repeats", "adds_detail"}:
            relation = "supports"
        if relation:
            edges.append(
                _edge(case_id, graph_run_id, left, right, relation, finding.explanation,
                      finding.confidence, "module2_finding")
            )

    return list(nodes.values()), edges


def _terms(value: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]{3,}", value.casefold())
        if term not in STOP_WORDS
    }


def _relation_candidates(case_id: UUID, graph_run_id: UUID, nodes: list[dict]) -> list[GraphRelationCandidate]:
    facts = [node for node in nodes if node["node_type"] == "fact"]
    issues = [node for node in nodes if node["node_type"] == "issue"]
    provisions = [node for node in nodes if node["node_type"] == "provision"]
    candidates: list[GraphRelationCandidate] = []
    seen_pairs: set[tuple[str, str]] = set()

    for issue in issues:
        issue_terms = _terms(issue["text"])
        pool: list[tuple[int, dict]] = []
        for related in facts + provisions:
            if related["node_type"] == "provision":
                provision_text = related["text"].strip().casefold()
                if len(provision_text) >= 4 and provision_text in issue["text"].casefold():
                    continue
            same_document = issue["source_document_id"] == related["source_document_id"]
            distance = abs(issue["unit_number"] - related["unit_number"]) if same_document else 10**6
            overlap = len(issue_terms & _terms(related["text"]))
            if not same_document and overlap == 0:
                continue
            if not (distance <= 1 or overlap >= 2):
                continue
            score = (100 if distance == 0 else 60 if distance == 1 else 0) + overlap
            pool.append((score, related))
        for _, related in sorted(pool, key=lambda pair: pair[0], reverse=True)[:5]:
            left_id, right_id = related["node_id"], issue["node_id"]
            if (left_id, right_id) in seen_pairs:
                continue
            seen_pairs.add((left_id, right_id))
            pair_id = _stable_id(str(case_id), str(graph_run_id), left_id, right_id)
            candidates.append(
                GraphRelationCandidate(
                    pair_id=pair_id,
                    left_node_id=left_id,
                    left_type=related["node_type"],
                    left_text=related["text"][:2_000],
                    right_node_id=right_id,
                    right_type=issue["node_type"],
                    right_text=issue["text"][:2_000],
                    left_evidence_quote=related["evidence_quote"][:2_000],
                    right_evidence_quote=issue["evidence_quote"][:2_000],
                    left_document_name=related["source_filename"],
                    right_document_name=issue["source_filename"],
                )
            )
    return candidates[:MAX_GRAPH_RELATION_CANDIDATES]


def _classify_candidates(case_id: UUID, graph_run_id: UUID, candidates: list[GraphRelationCandidate]) -> list[dict]:
    if not candidates:
        return []
    try:
        analyzer = GeminiCaseAnalyzer()
    except Exception as err:
        logger.warning("GeminiCaseAnalyzer unavailable for graph candidate classification: %s", err)
        return []
    edges = []
    by_id = {candidate.pair_id: candidate for candidate in candidates}
    for start in range(0, len(candidates), GRAPH_RELATION_BATCH_SIZE):
        batch = candidates[start : start + GRAPH_RELATION_BATCH_SIZE]
        try:
            result = analyzer.classify_graph_relations(batch)
            for relation in result.relations:
                candidate = by_id.get(relation.pair_id)
                if candidate is None:
                    continue
                edges.append(
                    _edge(
                        case_id, graph_run_id,
                        candidate.left_node_id, candidate.right_node_id,
                        relation.relation, relation.explanation, relation.confidence,
                        "llm_relation_classification",
                    )
                )
        except Exception as err:
            logger.warning("Gemini relation classification batch failed: %s; continuing with structural graph links.", err)
    return edges


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(settings.graph_embedding_model, device="cpu")
    except Exception as error:
        logger.warning(
            "Local semantic embeddings unavailable error_type=%s; graph search will use lexical ranking.",
            type(error).__name__,
        )
        return None


def _add_embeddings(nodes: list[dict]) -> str:
    """Attach real model embeddings, or explicitly mark this graph lexical-only."""
    dim = settings.graph_embedding_dimensions
    model = _embedding_model()
    if model is None:
        for node in nodes:
            node.pop("embedding", None)
        return "unavailable"
    try:
        for start in range(0, len(nodes), 64):
            batch = nodes[start : start + 64]
            vectors = model.encode(
                [f"{node['node_type']}: {node['label']}. {node['text']}" for node in batch],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            if len(vectors) != len(batch) or any(len(vector) != dim for vector in vectors):
                raise RuntimeError("Sentence-Transformers returned an unexpected embedding shape.")
            for node, vector in zip(batch, vectors, strict=True):
                node["embedding"] = [float(value) for value in vector]
        return "available"
    except Exception as error:
        logger.warning(
            "Local semantic embedding failed error_type=%s; graph will be searchable lexically.",
            type(error).__name__,
        )
        for node in nodes:
            node.pop("embedding", None)
        return "unavailable"


def _write_snapshot(case_id: UUID, graph_run_id: UUID, nodes: list[dict], edges: list[dict]) -> None:
    from neo4j import GraphDatabase

    if not graph_is_configured():
        raise RuntimeError("Enable the knowledge graph and configure Neo4j before building a graph.")
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        driver.verify_connectivity()
        dimension = settings.graph_embedding_dimensions
        with driver.session(database=settings.neo4j_database) as session:
            session.run(
                "CREATE CONSTRAINT knowledge_node_id_unique IF NOT EXISTS "
                "FOR (n:KnowledgeNode) REQUIRE n.node_id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE INDEX knowledge_node_case_id IF NOT EXISTS "
                "FOR (n:KnowledgeNode) ON (n.case_id)"
            ).consume()
            session.run(
                "CREATE VECTOR INDEX knowledge_node_embedding IF NOT EXISTS "
                f"FOR (n:KnowledgeNode) ON (n.embedding) OPTIONS {{indexConfig: "
                f"{{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}"
            ).consume()

            for start in range(0, len(nodes), GRAPH_NODE_WRITE_BATCH_SIZE):
                session.run(
                    "UNWIND $rows AS row MERGE (n:KnowledgeNode {node_id: row.node_id}) SET n += row",
                    rows=nodes[start : start + GRAPH_NODE_WRITE_BATCH_SIZE],
                ).consume()
            for start in range(0, len(edges), GRAPH_NODE_WRITE_BATCH_SIZE):
                session.run(
                    "UNWIND $rows AS row "
                    "MATCH (source:KnowledgeNode {node_id: row.source_id, case_id: $case_id}) "
                    "MATCH (target:KnowledgeNode {node_id: row.target_id, case_id: $case_id}) "
                    "MERGE (source)-[edge:GRAPH_RELATION {edge_id: row.edge_id}]->(target) "
                    "SET edge += row",
                    rows=edges[start : start + GRAPH_NODE_WRITE_BATCH_SIZE],
                    case_id=str(case_id),
                ).consume()
            session.run(
                "MATCH (n:KnowledgeNode {case_id: $case_id}) "
                "WHERE n.graph_run_id <> $graph_run_id DETACH DELETE n",
                case_id=str(case_id),
                graph_run_id=str(graph_run_id),
            ).consume()
    finally:
        driver.close()


def _snapshot_for_api(
    nodes: list[dict], edges: list[dict], *, embedding_status: str
) -> dict:
    return {
        "capabilities": {
            "semantic_embeddings": embedding_status,
            "graph_relationships": "available",
            "search_mode": "hybrid" if embedding_status == "available" else "lexical_only",
        },
        "nodes": [
            {key: value for key, value in node.items() if key != "embedding"}
            for node in nodes
        ],
        "edges": edges,
    }


def _hybrid_graph_scores(query: str, nodes: list[dict]) -> list[tuple[float, float, float, dict]]:
    """Use real local embeddings when available, otherwise rank by lexical overlap."""
    query_terms = _terms(query)
    model = _embedding_model()
    query_vector = None
    if model is not None:
        try:
            raw_vec = model.encode(
                [query], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            )[0]
            query_vector = [float(value) for value in raw_vec]
        except Exception as error:
            logger.warning("Graph query embedding unavailable error_type=%s; using lexical ranking.", type(error).__name__)
    query_norm = sum(value * value for value in query_vector) ** 0.5 if query_vector else 0.0

    scored = []
    for node in nodes:
        vector = node.get("embedding")
        semantic_score = 0.0
        has_semantic_score = (
            query_vector is not None
            and isinstance(vector, list)
            and len(vector) == len(query_vector)
            and query_norm > 0
        )
        if has_semantic_score:
            vector_norm = sum(float(value) * float(value) for value in vector) ** 0.5
            if vector_norm:
                semantic_score = sum(
                    left * float(right) for left, right in zip(query_vector, vector, strict=True)
                ) / (query_norm * vector_norm)
        node_terms = _terms(f"{node.get('label', '')} {node.get('text', '')} {node.get('evidence_quote', '')}")
        lexical_score = len(query_terms & node_terms) / max(len(query_terms), 1)
        # Convert cosine similarity from [-1, 1] to [0, 1] before blending.
        semantic_rank = max(0.0, min(1.0, (semantic_score + 1.0) / 2.0))
        blended_score = 0.8 * semantic_rank + 0.2 * lexical_score if has_semantic_score else lexical_score
        scored.append((blended_score, semantic_score, lexical_score, node))
    scored.sort(key=lambda item: (item[0], item[2], item[1]), reverse=True)
    return scored


def search_case_knowledge_graph(case_id: UUID, graph_run_id: UUID, query: str, top_k: int) -> tuple[list[dict], bool]:
    """Retrieve semantically and lexically relevant nodes plus their local graph context.

    All Neo4j reads are constrained by both case ID and graph run ID so this retrieval
    cannot mix nodes from another advocate matter or from an older graph snapshot.
    """
    from neo4j import GraphDatabase

    if not graph_is_configured():
        raise RuntimeError("The case knowledge graph is not configured.")
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as session:
            records = session.run(
                "MATCH (n:KnowledgeNode {case_id: $case_id, graph_run_id: $graph_run_id}) "
                "RETURN properties(n) AS node ORDER BY n.node_id LIMIT $limit",
                case_id=str(case_id),
                graph_run_id=str(graph_run_id),
                limit=MAX_GRAPH_SEARCH_NODES + 1,
            ).data()
            truncated = len(records) > MAX_GRAPH_SEARCH_NODES
            graph_nodes = [record["node"] for record in records[:MAX_GRAPH_SEARCH_NODES]]
            ranked = _hybrid_graph_scores(query, graph_nodes)[:top_k]
            selected_ids = [row[3]["node_id"] for row in ranked]
            edge_context = []
            if selected_ids:
                edge_context = session.run(
                    "UNWIND $node_ids AS node_id "
                    "MATCH (n:KnowledgeNode {node_id: node_id, case_id: $case_id, graph_run_id: $graph_run_id}) "
                    "-[r:GRAPH_RELATION]-(neighbor:KnowledgeNode {case_id: $case_id, graph_run_id: $graph_run_id}) "
                    "RETURN properties(n) AS selected, properties(r) AS relation, "
                    "properties(neighbor) AS related LIMIT $limit",
                    node_ids=selected_ids,
                    case_id=str(case_id),
                    graph_run_id=str(graph_run_id),
                    limit=MAX_GRAPH_CONTEXT_EDGES,
                ).data()
    finally:
        driver.close()

    context_by_node: dict[str, list[dict]] = defaultdict(list)
    for record in edge_context:
        context_by_node.setdefault(record["selected"]["node_id"], []).append({
            "relation": record["relation"].get("relation", "related"),
            "explanation": record["relation"].get("explanation", ""),
            "confidence": record["relation"].get("confidence", 0.0),
            "source_kind": record["relation"].get("source_kind", "unknown"),
            "source_node_id": record["relation"].get("source_id", ""),
            "related_node": {
                key: value for key, value in record["related"].items() if key != "embedding"
            },
        })

    results = []
    for score, semantic_score, lexical_score, node in ranked:
        results.append({
            "node": {key: value for key, value in node.items() if key != "embedding"},
            "score": round(score, 6),
            "semantic_score": round(semantic_score, 6),
            "lexical_score": round(lexical_score, 6),
            "related_context": context_by_node.get(node["node_id"], [])[:12],
        })
    return results, truncated


def process_case_knowledge_graph(graph_run_id: UUID) -> None:
    with SessionLocal() as db:
        run = db.get(CaseKnowledgeGraphRun, graph_run_id)
        if run is None:
            return
        case_id = run.case_id
        local_run_id = run.id
        run.status = "processing"
        run.error_message = None
        db.commit()
        failure_stage = "loading Module 2 results"
        try:
            analysis_run = db.scalar(
                select(CaseAnalysisRun)
                .where(
                    CaseAnalysisRun.id == run.analysis_run_id,
                    CaseAnalysisRun.case_id == run.case_id,
                    CaseAnalysisRun.status == "completed",
                )
                .options(
                    selectinload(CaseAnalysisRun.facts)
                    .joinedload(CaseAnalysisFact.source_unit)
                    .joinedload(DocumentTextUnit.document),
                    selectinload(CaseAnalysisRun.extraction_items)
                    .joinedload(CaseAnalysisExtractionItem.source_unit)
                    .joinedload(DocumentTextUnit.document),
                    selectinload(CaseAnalysisRun.findings)
                    .joinedload(CaseAnalysisFinding.left_fact),
                    selectinload(CaseAnalysisRun.findings)
                    .joinedload(CaseAnalysisFinding.right_fact),
                )
            )
            if analysis_run is None:
                raise ValueError("A completed Module 2 analysis is required before graph construction.")
            db.expunge_all()

            failure_stage = "building graph nodes and rule-based links"
            nodes, edges = _make_graph(case_id, local_run_id, analysis_run)
            candidates = _relation_candidates(case_id, local_run_id, nodes)
            failure_stage = "classifying ambiguous relationships with Gemini"
            edges.extend(_classify_candidates(case_id, local_run_id, candidates))
            if not nodes:
                raise ValueError("Module 2 returned no facts, issues, evidence, provisions, or parties to graph.")
            failure_stage = "generating local Sentence-Transformers embeddings"
            failure_stage = "generating local Sentence-Transformers embeddings (optional)"
            embedding_status = _add_embeddings(nodes)
            failure_stage = "writing nodes and relationships to Neo4j"
            _write_snapshot(case_id, local_run_id, nodes, edges)
            snapshot = _snapshot_for_api(nodes, edges, embedding_status=embedding_status)

            completed = db.get(CaseKnowledgeGraphRun, graph_run_id)
            if completed is None:
                # Case deletion can complete while the graph is being written
                # to Neo4j. Remove this late snapshot so it cannot survive as
                # an orphan for a case that no longer has a database record.
                delete_case_knowledge_graph(case_id, graph_run_id=local_run_id)
                return
            completed.graph_snapshot = snapshot
            completed.node_count = len(nodes)
            completed.edge_count = len(edges)
            completed.status = "completed"
            completed.completed_at = datetime.now(UTC)
            case = db.get(Case, completed.case_id)
            if case is not None:
                case.updated_at = datetime.now(UTC)
            db.commit()
        except Exception as error:  # noqa: BLE001 — vendor and document payloads must not reach job errors.
            logger.error(
                "Knowledge graph build failed run_id=%s stage=%s error_type=%s",
                graph_run_id,
                failure_stage,
                type(error).__name__,
            )
            db.rollback()
            try:
                # A write can fail after one or more Neo4j batches have
                # committed. Remove this partial run before marking it failed.
                delete_case_knowledge_graph(case_id, graph_run_id=local_run_id)
            except Exception as cleanup_error:  # noqa: BLE001 — retain the status update even if Neo4j is down.
                logger.error(
                    "Could not clean partial knowledge graph run_id=%s error_type=%s",
                    graph_run_id,
                    type(cleanup_error).__name__,
                )
            failed = db.get(CaseKnowledgeGraphRun, graph_run_id)
            if failed is None:
                return
            failed.status = "failed"
            failed.node_count = 0
            failed.edge_count = 0
            failed.graph_snapshot = None
            stage_guidance = {
                "loading Module 2 results": "Confirm that the latest case analysis completed successfully.",
                "building graph nodes and rule-based links": "Review the extracted facts, issues, and source links, then retry.",
                "classifying ambiguous relationships with Gemini": "Check Gemini configuration and retry the graph build.",
                "generating local Sentence-Transformers embeddings (optional)": "Install or configure the local embedding model to enable semantic search. The graph itself can still be built with lexical search.",
                "writing nodes and relationships to Neo4j": "Check that Neo4j is reachable and its credentials are valid, then retry.",
            }
            failed.error_message = (
                f"Knowledge graph construction failed while {failure_stage} "
                f"({type(error).__name__}). {stage_guidance.get(failure_stage, 'Check the graph service configuration and retry.')}"
            )
            failed.completed_at = datetime.now(UTC)
            db.commit()


def delete_case_knowledge_graph(case_id: UUID, *, graph_run_id: UUID | None = None) -> None:
    """Remove persisted case nodes, optionally limiting cleanup to one run."""
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        return
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        with driver.session(database=settings.neo4j_database) as session:
            if graph_run_id is None:
                session.run(
                    "MATCH (n:KnowledgeNode {case_id: $case_id}) DETACH DELETE n",
                    case_id=str(case_id),
                ).consume()
            else:
                session.run(
                    "MATCH (n:KnowledgeNode {case_id: $case_id, graph_run_id: $graph_run_id}) DETACH DELETE n",
                    case_id=str(case_id),
                    graph_run_id=str(graph_run_id),
                ).consume()
    finally:
        driver.close()
