"""Shared data contracts for Phase 12: Agentic RAG & Multi-Hop Reasoning."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts.retrieval import Candidate, Citation


class SubQuery(BaseModel):
    """An atomic sub-query decomposed from a complex multi-part user question."""

    query_text: str = Field(min_length=1, description="Targeted sub-query text")
    rationale: str = Field(description="Why this sub-query is necessary for the overall goal")
    hop_index: int = Field(ge=0, description="0-indexed hop execution order")


class DecompositionPlan(BaseModel):
    """Plan specifying whether and how a query is decomposed into multiple hops."""

    original_query: str
    is_multi_hop: bool = Field(description="True if query spans multiple topics/documents")
    sub_queries: list[SubQuery] = Field(default_factory=list)


class CRAGAssessment(BaseModel):
    """Corrective RAG (CRAG) reflection assessment of retrieved candidate relevance."""

    status: Literal["CONFIDENT", "AMBIGUOUS", "REFUSE"] = Field(
        description="Confidence status of retrieved context"
    )
    top_score: float = Field(description="Top cross-encoder relevance score")
    reformulated_query: str | None = Field(
        default=None, description="Corrective query formulated if status is AMBIGUOUS"
    )
    reason: str | None = Field(
        default=None, description="Rationale for confidence assessment or reformulation"
    )


class AgentStep(BaseModel):
    """A trace step representing an autonomous action taken by the RAG agent."""

    step_type: Literal[
        "decomposition",
        "sub_retrieval",
        "crag_reflection",
        "graph_traversal",
        "compaction",
        "rerank",
        "synthesis",
    ]
    step_index: int
    title: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgenticRetrieveResponse(BaseModel):
    """Structured response from the agentic multi-hop retrieval pipeline."""

    answer: str = Field(description="Synthesized multi-hop comparative answer")
    citations: list[Citation] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    crag_triggered: bool = False
    refused: bool = False
    top_score: float = 0.0
