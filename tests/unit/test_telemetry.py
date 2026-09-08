"""Unit tests for telemetry tracking and system metrics aggregation."""

from unittest.mock import MagicMock, patch

from contracts.metrics import QueryTelemetry, SystemMetrics
from services.telemetry.tracker import TelemetryTracker


def test_telemetry_contracts():
    record = QueryTelemetry(
        query_id="test_q_1",
        session_id="sess_1",
        query_text="What is the architecture?",
        dense_ms=15.2,
        sparse_ms=1.1,
        fusion_ms=0.5,
        rerank_ms=22.4,
        llm_ttft_ms=120.0,
        llm_gen_ms=450.0,
        total_ms=609.2,
        tokens_generated=80,
        tokens_per_sec=177.7,
        top_score=0.98,
        refused=False,
    )
    assert record.query_id == "test_q_1"
    assert record.tokens_per_sec == 177.7
    assert record.refused is False


def test_telemetry_tracker_accumulation():
    tracker = TelemetryTracker()

    # Record query 1 (successful)
    t1 = QueryTelemetry(
        query_id="q1",
        query_text="Test query 1",
        dense_ms=10.0,
        sparse_ms=2.0,
        fusion_ms=1.0,
        rerank_ms=20.0,
        llm_ttft_ms=100.0,
        llm_gen_ms=400.0,
        total_ms=533.0,
        tokens_generated=50,
        tokens_per_sec=125.0,
        top_score=0.95,
        refused=False,
    )
    tracker.record_query(t1)

    # Record query 2 (refusal)
    t2 = QueryTelemetry(
        query_id="q2",
        query_text="Out of domain question",
        dense_ms=12.0,
        sparse_ms=1.5,
        fusion_ms=0.5,
        rerank_ms=15.0,
        llm_ttft_ms=0.0,
        llm_gen_ms=0.0,
        total_ms=29.0,
        tokens_generated=0,
        tokens_per_sec=0.0,
        top_score=0.05,
        refused=True,
    )
    tracker.record_query(t2)

    recent = tracker.get_recent_telemetry(limit=2)
    assert len(recent) >= 2
    # Most recent first
    assert recent[0].query_id == "q2"
    assert recent[1].query_id == "q1"


def test_get_system_metrics():
    tracker = TelemetryTracker()

    mock_bm25 = MagicMock()
    mock_bm25.corpus_chunks = [1, 2, 3, 4, 5]

    with patch("requests.get") as mock_requests:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"result": {"points_count": 42}}
        mock_requests.return_value = mock_resp

        with patch("redis.Redis") as mock_redis_cls:
            mock_redis = MagicMock()
            mock_redis.llen.side_effect = [2, 0]  # 2 pending, 0 dlq
            mock_redis_cls.return_value = mock_redis

            metrics = tracker.get_system_metrics(
                qdrant_host="127.0.0.1",
                qdrant_port=6333,
                redis_host="127.0.0.1",
                redis_port=6379,
                bm25_store=mock_bm25,
            )

            assert isinstance(metrics, SystemMetrics)
            assert metrics.qdrant_points == 42
            assert metrics.bm25_chunks == 5
            assert metrics.redis_queue_depth == 2
            assert metrics.dlq_task_count == 0
            assert metrics.total_queries >= 2
            assert metrics.total_refusals >= 1
            assert metrics.uptime_seconds >= 0
