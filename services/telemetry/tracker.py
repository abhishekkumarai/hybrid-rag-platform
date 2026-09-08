"""Real-time telemetry and metrics tracker for hybrid RAG pipeline performance."""

from __future__ import annotations

import collections
import threading
import time
from typing import Any

import requests

from contracts.metrics import QueryTelemetry, SystemMetrics
from services.common.logger import get_logger

logger = get_logger("telemetry.tracker")


class TelemetryTracker:
    """Thread-safe telemetry accumulator and rolling performance analyzer."""

    _instance: TelemetryTracker | None = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> TelemetryTracker:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_history: int = 100) -> None:
        if getattr(self, "_initialized", False):
            return

        self._start_time = time.time()
        self._max_history = max_history
        self._history: collections.deque[QueryTelemetry] = collections.deque(maxlen=max_history)
        self._total_queries = 0
        self._total_refusals = 0
        self._mu = threading.Lock()
        self._initialized = True
        logger.info("Initialized TelemetryTracker singleton")

    def record_query(self, telemetry: QueryTelemetry) -> None:
        """Records a completed query's performance telemetry."""
        with self._mu:
            self._history.append(telemetry)
            self._total_queries += 1
            if telemetry.refused:
                self._total_refusals += 1

        logger.debug(
            f"Telemetry recorded: query_id={telemetry.query_id[:8]} "
            f"dense={telemetry.dense_ms:.1f}ms sparse={telemetry.sparse_ms:.1f}ms "
            f"rerank={telemetry.rerank_ms:.1f}ms total={telemetry.total_ms:.1f}ms "
            f"tok/s={telemetry.tokens_per_sec:.1f}"
        )

    def get_recent_telemetry(self, limit: int = 10) -> list[QueryTelemetry]:
        """Returns the most recent N query telemetry records."""
        with self._mu:
            records = list(self._history)
        return records[-limit:][::-1]

    def get_system_metrics(
        self,
        qdrant_host: str = "127.0.0.1",
        qdrant_port: int = 6333,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        bm25_store: Any = None,
    ) -> SystemMetrics:
        """Aggregates rolling averages and inspects live microservice states."""
        with self._mu:
            records = list(self._history)
            total_q = self._total_queries
            total_ref = self._total_refusals

        # Compute rolling averages
        if records:
            avg_ret = sum(r.dense_ms + r.sparse_ms + r.fusion_ms for r in records) / len(records)
            avg_rerank = sum(r.rerank_ms for r in records) / len(records)
            gen_records = [r for r in records if r.llm_gen_ms > 0]
            avg_gen = sum(r.llm_gen_ms for r in gen_records) / len(gen_records) if gen_records else 0.0
            tok_records = [r for r in records if r.tokens_per_sec > 0]
            avg_tok_sec = sum(r.tokens_per_sec for r in tok_records) / len(tok_records) if tok_records else 0.0
        else:
            avg_ret = 0.0
            avg_rerank = 0.0
            avg_gen = 0.0
            avg_tok_sec = 0.0

        # Query Qdrant Points
        qdrant_points = 0
        try:
            r = requests.get(f"http://{qdrant_host}:{qdrant_port}/collections/rag_docs", timeout=1.0)
            if r.status_code == 200:
                qdrant_points = r.json().get("result", {}).get("points_count", 0)
        except Exception:
            pass

        # Query BM25 Chunks
        bm25_chunks = 0
        if bm25_store and hasattr(bm25_store, "corpus_chunks"):
            bm25_chunks = len(bm25_store.corpus_chunks)

        # Query Redis Queue Depth & DLQ
        redis_pending = 0
        dlq_count = 0
        try:
            import redis

            r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=0.5)
            redis_pending = int(r_client.llen("rag:tasks:pending") or 0)
            dlq_count = int(r_client.llen("rag:tasks:dlq") or 0)
        except Exception:
            pass

        return SystemMetrics(
            uptime_seconds=round(time.time() - self._start_time, 1),
            total_queries=total_q,
            total_refusals=total_ref,
            avg_retrieval_ms=round(avg_ret, 2),
            avg_rerank_ms=round(avg_rerank, 2),
            avg_generation_ms=round(avg_gen, 2),
            avg_tokens_per_sec=round(avg_tok_sec, 2),
            qdrant_points=qdrant_points,
            bm25_chunks=bm25_chunks,
            redis_queue_depth=redis_pending,
            dlq_task_count=dlq_count,
            services={
                "qdrant": f"{qdrant_host}:{qdrant_port}",
                "redis": f"{redis_host}:{redis_port}",
            },
            recent_telemetry=records[-5:][::-1],
        )
