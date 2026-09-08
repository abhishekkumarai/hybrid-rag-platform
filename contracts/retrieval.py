"""Data contracts for Hybrid Retrieval and Cross-Encoder Reranking service."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Query payload submitted to RetrievalService.retrieve."""
    query_text: str = Field(min_length=1, description="Natural language search query")
    top_k: int = Field(default=20, ge=1, le=100, description="Number of hybrid candidates to retrieve")
    top_rerank: int = Field(default=6, ge=1, le=20, description="Final number of passages passed to LLM")
    min_rerank_score: float = Field(default=0.15, ge=0.0, le=1.0, description="Cutoff threshold for refusal")
    collection_name: str = Field(default="rag_docs", description="Target Qdrant collection name")
    doc_ids: list[str] | None = Field(default=None, description="Optional list of document IDs to constrain retrieval")


class Candidate(BaseModel):
    """Ranked document candidate originating from dual retrieval and reranking."""
    id: str = Field(description="Unique chunk identifier")
    doc_id: str = Field(description="Source document ID")
    page: int = Field(ge=1, description="Source page number")
    bbox: tuple[float, float, float, float] = Field(description="Bounding box on page (x0, y0, x1, y1)")
    text: str = Field(description="Chunk textual content")
    dense_rank: int | None = Field(default=None, description="Rank in dense Qdrant search (1-indexed)")
    sparse_rank: int | None = Field(default=None, description="Rank in sparse BM25s search (1-indexed)")
    rrf_score: float = Field(default=0.0, description="Reciprocal Rank Fusion score")
    rerank_score: float = Field(default=0.0, description="Cross-encoder relevance score (0.0 to 1.0)")
    headings: list[str] = Field(default_factory=list, description="Section hierarchy")
    is_table: bool = Field(default=False, description="Table chunk flag")
    is_figure: bool = Field(default=False, description="Figure chunk flag")
    image_path: str | None = Field(default=None, description="Relative path to figure PNG")
    caption: str | None = Field(default=None, description="Caption for table or figure")


class Citation(BaseModel):
    """Verified provenance citation with page and bounding box coordinates."""
    doc_id: str = Field(description="Document ID")
    page: int = Field(ge=1, description="Page number")
    bbox: tuple[float, float, float, float] = Field(description="Coordinates (x0, y0, x1, y1)")
    snippet: str = Field(description="Short text excerpt used as evidence")
    formatted_badge: str = Field(description="Badge string: [doc_id: Page p, (x0, y0, x1, y1)]")
    is_table: bool = Field(default=False, description="Table citation flag")
    is_figure: bool = Field(default=False, description="Figure citation flag")
    image_path: str | None = Field(default=None, description="Relative path to figure PNG if available")


class RetrieveResponse(BaseModel):
    """Response returned by RetrievalService.retrieve."""
    query: str = Field(description="Echo of search query")
    candidates: list[Candidate] = Field(description="Top reranked candidates")
    citations: list[Citation] = Field(description="Extracted citations for top candidates")
    refused: bool = Field(default=False, description="True if top rerank score < min_rerank_score")
    top_score: float = Field(default=0.0, description="Highest cross-encoder score among candidates")
    duration_ms: float = Field(ge=0.0, description="Total retrieval and reranking latency in ms")
