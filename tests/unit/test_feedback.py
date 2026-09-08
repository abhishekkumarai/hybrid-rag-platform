"""Unit tests for Phase 15: RAGOps Feedback, Continuous Evaluation, and Hard-Negative Mining."""

import tempfile
from pathlib import Path

from contracts.feedback import FeedbackRequest
from services.feedback.store import RAGOpsStore


def test_feedback_thumbs_up_recording():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RAGOpsStore(storage_dir=Path(tmpdir), enable_redis=False)

        req = FeedbackRequest(
            session_id="sess_1",
            query_text="What is the dense retrieval latency of RTX 3050?",
            response_text="The dense latency is 18.5 ms.",
            citations=[{"doc_id": "bench_1", "text": "RTX 3050 dense latency is 18.5 ms", "score": 0.99}],
            rating="thumbs_up",
            comment="Accurate and fast response",
        )

        record = store.record_feedback(req)
        assert record.id is not None
        assert record.rating == "thumbs_up"
        assert record.comment == "Accurate and fast response"

        summary = store.get_summary()
        assert summary.total_feedback == 1
        assert summary.thumbs_up == 1
        assert summary.thumbs_down == 0
        assert summary.satisfaction_rate_pct == 100.0
        assert summary.hard_negatives_count == 0


def test_feedback_thumbs_down_hard_negative_mining():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RAGOpsStore(storage_dir=Path(tmpdir), enable_redis=False)

        req = FeedbackRequest(
            session_id="sess_2",
            query_text="Where did Abhishek work in 2020?",
            response_text="Abhishek worked at Syngene in 2020.",
            citations=[
                {"doc_id": "resume_1", "text": "Syngene International Senior AI Engineer 2024-Present", "score": 0.42},
                {"doc_id": "resume_1", "text": "Tata Consultancy Services 2019-2022", "score": 0.38},
            ],
            rating="thumbs_down",
            comment="The year was incorrect.",
        )

        record = store.record_feedback(req)
        assert record.rating == "thumbs_down"

        summary = store.get_summary()
        assert summary.total_feedback == 1
        assert summary.thumbs_up == 0
        assert summary.thumbs_down == 1
        assert summary.satisfaction_rate_pct == 0.0
        assert summary.hard_negatives_count == 2  # 2 citations mined as hard negatives

        # Export active learning dataset
        dataset = store.export_training_dataset()
        assert len(dataset) == 2
        assert dataset[0]["query"] == "Where did Abhishek work in 2020?"
        assert dataset[0]["source"] == "thumbs_down"
        assert dataset[0]["negative_score"] in (0.42, 0.38)


def test_hard_negative_direct_recording():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RAGOpsStore(storage_dir=Path(tmpdir), enable_redis=False)

        sample = store.record_hard_negative(
            query_text="Quantum encryption key size",
            negative_doc_id="doc_crypto",
            negative_text="Standard AES-256 symmetric cipher details",
            negative_score=0.22,
            source="crag_refutation",
        )

        assert sample.id is not None
        assert sample.source == "crag_refutation"

        summary = store.get_summary()
        assert summary.hard_negatives_count == 1

        dataset = store.export_training_dataset()
        assert len(dataset) == 1
        assert dataset[0]["source"] == "crag_refutation"
        assert dataset[0]["negative_score"] == 0.22
