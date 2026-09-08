"""Entity and Relationship Extractor for Phase 13 GraphRAG.

Performs deterministic local entity and relation extraction from text passages and chunks,
preserving provenance coordinates (doc_id, chunk_id, page, bounding box).
"""

from __future__ import annotations

import re
import time
from typing import Sequence

from contracts.chunk import Chunk
from contracts.graph import Entity, GraphExtractionResult, Relation
from services.common.logger import get_logger

logger = get_logger("graph.extractor")

# Known entity catalogs for fast deterministic classification
KNOWN_HARDWARE = {
    "rtx 3050": "NVIDIA RTX 3050",
    "rtx 3050 laptop": "NVIDIA RTX 3050",
    "nvidia rtx 3050": "NVIDIA RTX 3050",
    "rtx 4090": "NVIDIA RTX 4090",
    "nvidia gpu": "NVIDIA GPU",
    "gpu": "GPU",
    "cpu": "CPU",
    "vram": "VRAM",
    "system ram": "System RAM",
    "ram": "RAM",
    "onnx runtime": "ONNX Runtime",
}

KNOWN_SOFTWARE = {
    "qdrant": "Qdrant",
    "redis": "Redis",
    "ollama": "Ollama",
    "docling": "Docling",
    "rapidocr": "RapidOCR",
    "pymupdf": "PyMuPDF",
    "flashrank": "FlashRank",
    "bm25": "BM25",
    "bm25s": "BM25s",
    "fastapi": "FastAPI",
    "langflow": "Langflow",
    "docker": "Docker",
    "postgresql": "PostgreSQL",
    "python": "Python",
    "networkx": "NetworkX",
    "pydantic": "Pydantic",
    "llama3.1": "Llama 3.1",
    "llama3.2": "Llama 3.2",
    "bge-m3": "BGE-M3",
}

KNOWN_ORGANIZATIONS = {
    "nvidia": "NVIDIA",
    "syngene": "Syngene",
    "bristol myers squibb": "Bristol Myers Squibb",
    "meta": "Meta",
    "google": "Google",
}

KNOWN_CONCEPTS = {
    "rag": "RAG",
    "hybrid rag": "Hybrid RAG",
    "crag": "CRAG",
    "corrective rag": "Corrective RAG",
    "reciprocal rank fusion": "Reciprocal Rank Fusion",
    "rrf": "RRF",
    "hnsw": "HNSW",
    "dlq": "Dead-Letter Queue (DLQ)",
    "dead-letter queue": "Dead-Letter Queue (DLQ)",
    "active learning": "Active Learning",
    "visual provenance": "Visual Provenance",
    "graphrag": "GraphRAG",
    "contextual compression": "Contextual Compression",
    "multi-hop": "Multi-Hop Reasoning",
}

# Regex for metrics & quantitative specs (e.g. 6GB, 16GB, 8K, 512 tokens, 18.5ms, 0.15 score)
METRIC_REGEX = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:gb|mb|tb|ms|sec|tokens|k|mhz|ghz|%|dpi))\b",
    re.IGNORECASE,
)

# Common predicate patterns for triple extraction
RELATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "X has/features/allocates Y (VRAM/memory/spec)"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:has|features|allocates|equipped with|configured with)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "has_specification",
    ),
    # "X runs on / executes on Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:runs on|executes on|operates on|deployed on)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "runs_on",
    ),
    # "X uses / utilizes / powered by Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:uses|utilizes|is powered by|leverages)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "uses",
    ),
    # "X indexes into / stores in Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:indexes into|stores in|persists to|indexed into)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "indexes_into",
    ),
    # "X evaluates / reflects on / classifies Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:evaluates|reflects on|classifies|grades)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "evaluates",
    ),
    # "X combines / fuses / joins Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:combines|fuses|merges|joins)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "combines",
    ),
    # "X achieves / yields / measures Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:achieves|yields|measures|reaches|recorded)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "achieves",
    ),
    # "X serves / exposes / provides Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:serves|exposes|provides|hosts)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "exposes",
    ),
    # "X connects to / interfaces with Y"
    (
        re.compile(
            r"([A-Za-z0-9_\-\s]{2,40})\s+(?:connects to|interfaces with|links to)\s+([A-Za-z0-9_\-\.\s]{2,40})",
            re.IGNORECASE,
        ),
        "connects_to",
    ),
]


class EntityRelationshipExtractor:
    """Deterministic, high-speed entity and relation extractor for GraphRAG."""

    def __init__(self) -> None:
        self._build_vocab_index()

    def _build_vocab_index(self) -> None:
        self.vocab_map: dict[str, tuple[str, str]] = {}
        for k, v in KNOWN_HARDWARE.items():
            self.vocab_map[k] = (v, "HARDWARE")
        for k, v in KNOWN_SOFTWARE.items():
            self.vocab_map[k] = (v, "SOFTWARE")
        for k, v in KNOWN_ORGANIZATIONS.items():
            self.vocab_map[k] = (v, "ORGANIZATION")
        for k, v in KNOWN_CONCEPTS.items():
            self.vocab_map[k] = (v, "CONCEPT")

    def extract_entities(
        self,
        text: str,
        doc_id: str | None = None,
        chunk_id: str | None = None,
        page: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[Entity]:
        """Extracts recognized named entities from text."""
        entities_dict: dict[str, Entity] = {}
        text_lower = text.lower()

        # 1. Match known entities
        for phrase, (normalized_name, category) in self.vocab_map.items():
            # word boundary search
            pattern = rf"\b{re.escape(phrase)}\b"
            if re.search(pattern, text_lower):
                if normalized_name not in entities_dict:
                    entities_dict[normalized_name] = Entity(
                        name=normalized_name,
                        category=category,
                        doc_id=doc_id,
                        chunk_id=chunk_id,
                        page=page,
                        bbox=bbox,
                    )

        # 2. Match metrics & quantitative specs
        for m in METRIC_REGEX.finditer(text):
            metric_val = m.group(1).strip()
            if metric_val not in entities_dict:
                entities_dict[metric_val] = Entity(
                    name=metric_val,
                    category="METRIC",
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    page=page,
                    bbox=bbox,
                )

        # 3. Capitalized Proper Noun heuristics (2 to 3 capitalized words)
        proper_nouns = re.findall(r"\b([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){1,2})\b", text)
        for pn in proper_nouns:
            clean_pn = pn.strip()
            if (
                clean_pn not in entities_dict
                and clean_pn.lower() not in ["the", "this", "that", "there"]
                and len(clean_pn) > 3
            ):
                entities_dict[clean_pn] = Entity(
                    name=clean_pn,
                    category="CONCEPT",
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    page=page,
                    bbox=bbox,
                )

        return list(entities_dict.values())

    def extract_relations(
        self,
        text: str,
        entities: Sequence[Entity] | None = None,
        doc_id: str | None = None,
        chunk_id: str | None = None,
        page: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[Relation]:
        """Extracts directional relations between entities found in text."""
        if entities is None:
            entities = self.extract_entities(text, doc_id=doc_id, chunk_id=chunk_id, page=page, bbox=bbox)

        if len(entities) < 2:
            return []

        entity_names = {e.name.lower(): e.name for e in entities}
        relations: list[Relation] = []
        seen_triples: set[tuple[str, str, str]] = set()

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sent in sentences:
            sent_clean = sent.strip()
            if not sent_clean:
                continue

            # Identify which entities appear in this sentence
            sent_entities: list[str] = []
            for e_low, e_norm in entity_names.items():
                if re.search(rf"\b{re.escape(e_low)}\b", sent_clean.lower()):
                    sent_entities.append(e_norm)

            if len(sent_entities) < 2:
                continue

            # Pattern-based extraction
            matched_by_pattern = False
            for pat, predicate in RELATION_PATTERNS:
                for match in pat.finditer(sent_clean):
                    raw_subj = match.group(1).strip()
                    raw_obj = match.group(2).strip()

                    # Resolve to entities if possible
                    subj_match = self._best_matching_entity(raw_subj, sent_entities)
                    obj_match = self._best_matching_entity(raw_obj, sent_entities)

                    if subj_match and obj_match and subj_match != obj_match:
                        triple_key = (subj_match, predicate, obj_match)
                        if triple_key not in seen_triples:
                            seen_triples.add(triple_key)
                            relations.append(
                                Relation(
                                    source=subj_match,
                                    predicate=predicate,
                                    target=obj_match,
                                    doc_id=doc_id,
                                    chunk_id=chunk_id,
                                    page=page,
                                    bbox=bbox,
                                    weight=1.0,
                                    evidence_snippet=sent_clean[:200],
                                )
                            )
                            matched_by_pattern = True

            # Co-occurrence association if no explicit pattern matched
            if not matched_by_pattern and len(sent_entities) >= 2:
                # Pair primary entity with secondary entity as 'associated_with'
                primary = sent_entities[0]
                for other in sent_entities[1:]:
                    triple_key = (primary, "associated_with", other)
                    if triple_key not in seen_triples:
                        seen_triples.add(triple_key)
                        relations.append(
                            Relation(
                                source=primary,
                                predicate="associated_with",
                                target=other,
                                doc_id=doc_id,
                                chunk_id=chunk_id,
                                page=page,
                                bbox=bbox,
                                weight=0.6,
                                evidence_snippet=sent_clean[:200],
                            )
                        )

        return relations

    def _best_matching_entity(self, text_fragment: str, candidate_entities: list[str]) -> str | None:
        """Finds if a text fragment closely corresponds to any candidate entity."""
        frag_low = text_fragment.lower().strip()
        for cand in candidate_entities:
            cand_low = cand.lower()
            if cand_low in frag_low or frag_low in cand_low:
                return cand
        return None

    def extract_from_chunk(self, chunk: Chunk) -> GraphExtractionResult:
        """Extracts entities and relations from a single document Chunk."""
        start = time.perf_counter()
        entities = self.extract_entities(
            text=chunk.text,
            doc_id=chunk.doc_id,
            chunk_id=chunk.id,
            page=chunk.page,
            bbox=chunk.bbox,
        )
        relations = self.extract_relations(
            text=chunk.text,
            entities=entities,
            doc_id=chunk.doc_id,
            chunk_id=chunk.id,
            page=chunk.page,
            bbox=chunk.bbox,
        )
        duration_ms = (time.perf_counter() - start) * 1000

        return GraphExtractionResult(
            entities=entities,
            relations=relations,
            doc_id=chunk.doc_id,
            chunk_id=chunk.id,
            duration_ms=round(duration_ms, 2),
        )

    def extract_from_chunks(self, chunks: Sequence[Chunk]) -> GraphExtractionResult:
        """Extracts entities and relations across a batch of chunks."""
        start = time.perf_counter()
        all_entities_map: dict[str, Entity] = {}
        all_relations: list[Relation] = []
        seen_triples: set[tuple[str, str, str]] = set()

        for chunk in chunks:
            res = self.extract_from_chunk(chunk)
            for e in res.entities:
                if e.name not in all_entities_map:
                    all_entities_map[e.name] = e
            for r in res.relations:
                key = (r.source, r.predicate, r.target)
                if key not in seen_triples:
                    seen_triples.add(key)
                    all_relations.append(r)

        duration_ms = (time.perf_counter() - start) * 1000
        return GraphExtractionResult(
            entities=list(all_entities_map.values()),
            relations=all_relations,
            duration_ms=round(duration_ms, 2),
        )
