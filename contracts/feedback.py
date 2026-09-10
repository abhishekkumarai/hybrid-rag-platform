"""Shared data contracts for Phase 15: Continuous Evaluation & Active Learning (RAGOps)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

FeedbackRating = Literal["thumbs_up", "thumbs_down"]


class FeedbackRequest(BaseModel):
    """User feedback submission for a specific chat answer."""

    session_id: str | None = Field(default=None, description="Session ID if conversational")
    query_text: str = Field(min_length=1, description="Original user prompt")
    response_text: str = Field(min_length=1, description="Model generated response")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="Citations delivered with answer")
    rating: FeedbackRating = Field(description="thumbs_up (helpful) or thumbs_down (inaccurate/hallucinated)")
    comment: str | None = Field(default=None, description="Optional user textual critique")


class FeedbackRecord(BaseModel):
    """Persisted feedback record with metadata."""

    id: str = Field(description="Unique feedback UUID")
    timestamp: str = Field(description="ISO timestamp")
    session_id: str | None = None
    query_text: str
    response_text: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    rating: FeedbackRating
    comment: str | None = None


class HardNegativeRecord(BaseModel):
    """An active learning hard-negative sample mined for reranker/embedding fine-tuning."""

    id: str = Field(description="Sample UUID")
    timestamp: str = Field(description="ISO timestamp")
    session_id: str | None = Field(default=None, description="Session ID if conversational")
    query_text: str = Field(description="The query that retrieved the negative")
    positive_doc_id: str | None = Field(default=None, description="Document ID of positive passage if known")
    positive_text: str | None = Field(default=None, description="Relevant passage text")
    negative_doc_id: str = Field(description="Document ID of unhelpful/irrelevant candidate")
    negative_text: str = Field(description="Irrelevant passage text erroneously retrieved/scored high")
    negative_score: float = Field(description="Cross-encoder or retrieval score")
    source: str = Field(description="Source of mining: 'thumbs_down', 'crag_refutation', or 'refusal'")


class RAGOpsSummary(BaseModel):
    """Aggregated continuous evaluation and active learning metrics."""

    total_feedback: int = 0
    thumbs_up: int = 0
    thumbs_down: int = 0
    satisfaction_rate_pct: float = 0.0
    hard_negatives_count: int = 0
