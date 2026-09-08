"""Shared data contracts for Phase 14: Contextual Compression & Adaptive Token Budget Compactor."""

from __future__ import annotations

from pydantic import BaseModel, Field

from contracts.retrieval import Candidate


class CompressedChunk(BaseModel):
    """A chunk compressed via sentence salience selection, redundancy deduplication, and column pruning."""

    id: str = Field(description="Unique chunk identifier")
    doc_id: str = Field(description="Source document ID")
    page: int = Field(ge=1, description="Source page number")
    bbox: tuple[float, float, float, float] = Field(description="Preserved bounding box (x0, y0, x1, y1)")
    original_text: str = Field(description="Full uncompressed chunk text")
    compressed_text: str = Field(description="Compressed salient text excerpt")
    original_tokens: int = Field(ge=0, description="Approximate token count before compression")
    compressed_tokens: int = Field(ge=0, description="Approximate token count after compression")
    compression_ratio: float = Field(
        ge=0.0, le=1.0, description="Ratio of compressed to original tokens (e.g. 0.45 = 55% saved)"
    )
    is_table: bool = Field(default=False, description="Whether this chunk represents a structured table")
    is_figure: bool = Field(default=False, description="Whether this chunk represents a figure crop")
    headings: list[str] = Field(default_factory=list, description="Preserved section headings")
    retained_sentences: list[str] = Field(default_factory=list, description="List of salient sentences retained")
    score: float = Field(default=0.0, description="Relevance score of the chunk")


class CompactedContext(BaseModel):
    """Result of context compression across multiple retrieved candidate passages."""

    query: str = Field(description="Search or decomposition query")
    chunks: list[CompressedChunk] = Field(
        default_factory=list, description="Retained compressed chunks within budget"
    )
    total_original_tokens: int = Field(ge=0, description="Sum of original candidate tokens")
    total_compressed_tokens: int = Field(ge=0, description="Sum of compressed context tokens")
    overall_compression_ratio: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Overall compressed/original token ratio"
    )
    budget_tokens: int = Field(ge=1, description="Strict context token envelope limit (e.g. 3072)")
    dropped_chunks_count: int = Field(default=0, ge=0, description="Chunks dropped due to budget or low score")
    deduplicated_sentences_count: int = Field(
        default=0, ge=0, description="Redundant duplicate sentences pruned across documents"
    )
    pruned_table_columns_count: int = Field(
        default=0, ge=0, description="Irrelevant table columns stripped from wide tables"
    )
    formatted_prompt_context: str = Field(
        default="", description="Ready-to-inject markdown prompt context string"
    )
    duration_ms: float = Field(ge=0.0, description="Compactor latency in milliseconds")


class CompactorRequest(BaseModel):
    """Payload for contextual compression request."""

    query: str = Field(min_length=1, description="Natural language user question")
    candidates: list[Candidate] = Field(
        default_factory=list, description="Candidate chunks retrieved by hybrid/agentic search"
    )
    budget_tokens: int = Field(
        default=3072, ge=16, le=32768, description="Target token budget envelope for LLM context"
    )
    deduplicate: bool = Field(
        default=True, description="Enable cross-passage redundancy deduplication"
    )
    prune_tables: bool = Field(
        default=True, description="Enable selective column pruning for wide tables"
    )
    min_sentence_score: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Minimum relevance score to keep an individual sentence"
    )
