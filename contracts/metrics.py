"""Pydantic data contracts for real-time query telemetry and system observability."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


class QueryTelemetry(BaseModel):
    """Detailed latency, throughput, and outcome telemetry for a single query."""

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    query_text: str
    dense_ms: float = 0.0
    sparse_ms: float = 0.0
    fusion_ms: float = 0.0
    rerank_ms: float = 0.0
    llm_ttft_ms: float = 0.0
    llm_gen_ms: float = 0.0
    total_ms: float = 0.0
    tokens_generated: int = 0
    tokens_per_sec: float = 0.0
    refused: bool = False
    top_score: float = 0.0
    citations_count: int = 0
    timestamp: float = Field(default_factory=time.time)


class SystemMetrics(BaseModel):
    """Aggregated system performance and health metrics."""

    uptime_seconds: float = 0.0
    total_queries: int = 0
    total_refusals: int = 0
    avg_retrieval_ms: float = 0.0
    avg_rerank_ms: float = 0.0
    avg_generation_ms: float = 0.0
    avg_tokens_per_sec: float = 0.0
    qdrant_points: int = 0
    bm25_chunks: int = 0
    redis_queue_depth: int = 0
    dlq_task_count: int = 0
    services: dict[str, Any] = Field(default_factory=dict)
    recent_telemetry: list[QueryTelemetry] = Field(default_factory=list)
