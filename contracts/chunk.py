"""Data contracts for Chunking and Dual Indexing service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """Enriched, token-bounded chunk ready for dense and sparse indexing."""
    id: str = Field(description="Unique chunk identifier (doc_id_c{index})")
    doc_id: str = Field(description="Identifier of source document")
    page: int = Field(ge=1, description="Primary source page number")
    page_end: int = Field(ge=1, description="Ending page number if spanning multiple pages")
    bbox: tuple[float, float, float, float] = Field(
        description="Bounding box coordinates (x0, y0, x1, y1) on the primary page"
    )
    text: str = Field(description="Enriched chunk text (with section breadcrumbs if applicable)")
    raw_text: str = Field(description="Raw text without added hierarchy breadcrumbs")
    token_count: int = Field(ge=1, le=512, description="Estimated token count (hard capped at 512)")
    headings: list[str] = Field(default_factory=list, description="Parent heading hierarchy path")
    is_table: bool = Field(default=False, description="Flag indicating chunk contains a serialized table")
    is_figure: bool = Field(default=False, description="Flag indicating chunk contains an extracted figure/image")
    image_path: str | None = Field(default=None, description="Relative path to extracted figure PNG image")
    caption: str | None = Field(default=None, description="Associated table or figure caption")
    table_markdown: str | None = Field(default=None, description="Clean markdown table content if table chunk")
    meta: dict[str, Any] = Field(default_factory=dict, description="Additional block metadata")


class IndexRequest(BaseModel):
    """Request payload for IndexingService.index."""
    doc_id: str = Field(description="Identifier of document being indexed")
    chunks: list[Chunk] = Field(description="List of chunks to index")
    collection_name: str = Field(default="rag_docs", description="Target Qdrant collection name")


class IndexResponse(BaseModel):
    """Response payload returned by IndexingService.index."""
    doc_id: str = Field(description="Identifier of indexed document")
    indexed_count: int = Field(ge=0, description="Total chunks indexed in dense and sparse stores")
    dense_indexed: bool = Field(default=True, description="Success status for Qdrant HNSW")
    sparse_indexed: bool = Field(default=True, description="Success status for BM25s")
    graph_indexed: bool = Field(default=True, description="Success status for Knowledge Graph indexing")
    duration_ms: float = Field(ge=0.0, description="Total indexing duration in milliseconds")
