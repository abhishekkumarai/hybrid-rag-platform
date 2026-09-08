"""Shared data contracts for Phase 13: Graph-Augmented RAG (GraphRAG)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Named entity extracted from text or layout chunks."""

    name: str = Field(min_length=1, description="Normalized entity name/identifier")
    category: str = Field(
        default="CONCEPT",
        description="Entity type: HARDWARE, SOFTWARE, METRIC, ORGANIZATION, CONCEPT, or DOCUMENT",
    )
    doc_id: str | None = Field(default=None, description="Source document ID")
    chunk_id: str | None = Field(default=None, description="Source chunk ID")
    page: int | None = Field(default=None, ge=1, description="Source page number")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="Bounding box on page (x0, y0, x1, y1)"
    )
    properties: dict[str, Any] = Field(default_factory=dict, description="Arbitrary entity attributes")


class Relation(BaseModel):
    """Directional predicate relation between two entities."""

    source: str = Field(min_length=1, description="Source entity name")
    predicate: str = Field(min_length=1, description="Directional predicate or relationship type")
    target: str = Field(min_length=1, description="Target entity name")
    doc_id: str | None = Field(default=None, description="Source document ID")
    chunk_id: str | None = Field(default=None, description="Source chunk ID")
    page: int | None = Field(default=None, ge=1, description="Source page number")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="Bounding box on page (x0, y0, x1, y1)"
    )
    weight: float = Field(default=1.0, ge=0.0, description="Edge weight / confidence score")
    evidence_snippet: str | None = Field(
        default=None, description="Text passage evidencing this relationship"
    )


class GraphNeighborhood(BaseModel):
    """Local subgraph neighborhood surrounding one or more focal entities."""

    center_entities: list[str] = Field(description="Focal entity names queried")
    entities: list[Entity] = Field(default_factory=list, description="Discovered entities in neighborhood")
    relations: list[Relation] = Field(default_factory=list, description="Interconnecting relations")
    connected_chunk_ids: list[str] = Field(
        default_factory=list, description="IDs of chunks supporting this subgraph"
    )
    depth: int = Field(default=1, ge=1, description="Traversal hop depth")


class GraphSearchQuery(BaseModel):
    """Payload for knowledge graph traversal queries."""

    query_text: str = Field(min_length=1, description="Natural language question or entity query")
    max_hops: int = Field(default=2, ge=1, le=5, description="Maximum traversal depth from focal entities")
    max_entities: int = Field(default=20, ge=1, le=100, description="Maximum entities in returned subgraph")
    min_edge_weight: float = Field(default=0.1, ge=0.0, description="Minimum edge weight threshold")


class GraphCommunity(BaseModel):
    """A detected modular community of strongly connected entities."""

    community_id: int = Field(ge=0, description="Unique community index")
    name: str = Field(default="", description="Auto-generated descriptive label or top central entity")
    entities: list[str] = Field(description="Entity names belonging to this community")
    summary: str = Field(default="", description="Relational summary of this community's theme")


class GraphExtractionResult(BaseModel):
    """Result of entity and relation extraction from text or chunks."""

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    doc_id: str | None = None
    chunk_id: str | None = None
    duration_ms: float = 0.0


class GraphRAGResponse(BaseModel):
    """Result of Graph-Augmented RAG traversal for a given query."""

    query: str = Field(description="Original query text")
    matched_entities: list[Entity] = Field(
        default_factory=list, description="Entities identified directly in query"
    )
    relations: list[Relation] = Field(
        default_factory=list, description="Traversed relations forming relational evidence"
    )
    subgraph_text: str = Field(
        default="", description="Formatted relational markdown triples ready for prompt synthesis"
    )
    connected_chunk_ids: list[str] = Field(
        default_factory=list, description="Chunk IDs referenced by the subgraph"
    )
    communities: list[GraphCommunity] = Field(
        default_factory=list, description="Relevant detected entity communities"
    )
    duration_ms: float = Field(ge=0.0, description="Graph traversal and synthesis latency in ms")
