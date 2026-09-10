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

    def _sync_with_redis(self, redis_host: str, redis_port: int) -> None:
        """Hydrates history from Redis to persist across container restarts."""
        try:
            import redis

            r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=1.0, decode_responses=True)
            raw_records = r_client.lrange("rag:telemetry:history", 0, self._max_history - 1)
            if raw_records:
                with self._mu:
                    self._history.clear()
                    self._total_queries = int(r_client.get("rag:telemetry:total_queries") or 0)
                    self._total_refusals = int(r_client.get("rag:telemetry:total_refusals") or 0)
                    for item in reversed(raw_records):
                        try:
                            self._history.append(QueryTelemetry.model_validate_json(item))
                        except Exception:
                            pass
        except Exception:
            pass

    def record_query(self, telemetry: QueryTelemetry, redis_host: str | None = None, redis_port: int | None = None) -> None:
        """Records a completed query's performance telemetry and persists to Redis."""
        with self._mu:
            self._history.append(telemetry)
            self._total_queries += 1
            if telemetry.refused:
                self._total_refusals += 1

        # Persist to Redis if available
        if redis_host and redis_port:
            try:
                import redis

                r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=0.5)
                r_client.lpush("rag:telemetry:history", telemetry.model_dump_json())
                r_client.ltrim("rag:telemetry:history", 0, self._max_history - 1)
                r_client.incr("rag:telemetry:total_queries")
                if telemetry.refused:
                    r_client.incr("rag:telemetry:total_refusals")
                if telemetry.session_id:
                    r_client.lpush(f"rag:telemetry:session:{telemetry.session_id}", telemetry.model_dump_json())
                    r_client.ltrim(f"rag:telemetry:session:{telemetry.session_id}", 0, self._max_history - 1)
            except Exception:
                pass

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
        session_id: str | None = None,
    ) -> SystemMetrics:
        """Aggregates rolling averages and inspects live microservice states, optionally scoped to a session."""
        with self._mu:
            if session_id:
                records = [r for r in self._history if r.session_id == session_id]
                total_q = len(records)
                total_ref = sum(1 for r in records if r.refused)
                # If memory has no records for this session, query Redis
                if not records and redis_host and redis_port:
                    try:
                        import redis

                        r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=0.5, decode_responses=True)
                        raw_sess_records = r_client.lrange(f"rag:telemetry:session:{session_id}", 0, 49)
                        if raw_sess_records:
                            for item in raw_sess_records:
                                try:
                                    rec = QueryTelemetry.model_validate_json(item)
                                    records.append(rec)
                                    if rec not in self._history:
                                        self._history.append(rec)
                                except Exception:
                                    pass
                            total_q = len(records)
                            total_ref = sum(1 for r in records if r.refused)
                    except Exception:
                        pass
            else:
                if not self._history and redis_host and redis_port:
                    self._sync_with_redis(redis_host, redis_port)
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
