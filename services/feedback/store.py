"""RAGOps Continuous Evaluation & Active Learning Store for Phase 15."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.feedback import (
    FeedbackRecord,
    FeedbackRequest,
    HardNegativeRecord,
    RAGOpsSummary,
)
from services.common.logger import get_logger

logger = get_logger("ragops.store")

RAGOPS_DIR = Path("data/ragops")
FEEDBACK_FILE = RAGOPS_DIR / "feedback.jsonl"
HARD_NEGATIVES_FILE = RAGOPS_DIR / "hard_negatives.jsonl"


class RAGOpsStore:
    """Manages user feedback persistence, continuous evaluation, and hard-negative mining."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        storage_dir: Path | None = None,
        enable_redis: bool = True,
    ) -> None:
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.storage_dir = storage_dir or RAGOPS_DIR
        self.feedback_file = self.storage_dir / "feedback.jsonl"
        self.hard_negatives_file = self.storage_dir / "hard_negatives.jsonl"
        self._ensure_storage_dir()
        self._redis: Any = None
        if enable_redis and redis_host:
            self._init_redis()

    def _ensure_storage_dir(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _init_redis(self) -> None:
        try:
            import redis
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                socket_timeout=1.0,
                decode_responses=True,
            )
            client.ping()
            self._redis = client
            logger.info(f"Connected to Redis RAGOps cache at {self.redis_host}:{self.redis_port}")
        except Exception as exc:
            logger.warning(f"Redis unavailable for RAGOps ({exc}); using disk JSONL storage")
            self._redis = None

    def record_feedback(self, request: FeedbackRequest) -> FeedbackRecord:
        """Records user feedback and triggers hard-negative mining on thumbs-down."""
        now_iso = datetime.now(timezone.utc).isoformat()
        rec_id = str(uuid.uuid4())
        record = FeedbackRecord(
            id=rec_id,
            timestamp=now_iso,
            session_id=request.session_id,
            query_text=request.query_text,
            response_text=request.response_text,
            citations=request.citations,
            rating=request.rating,
            comment=request.comment,
        )

        # 1. Append to JSONL file
        try:
            with open(self.feedback_file, "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        except Exception as exc:
            logger.error(f"Failed to append feedback to disk: {exc}")

        # 2. Cache in Redis
        if self._redis:
            try:
                self._redis.hset(f"rag:feedback:{rec_id}", mapping={
                    "id": rec_id,
                    "timestamp": now_iso,
                    "rating": request.rating,
                    "query": request.query_text,
                })
                self._redis.rpush("rag:feedback:all", rec_id)
                if request.rating == "thumbs_up":
                    self._redis.incr("rag:metrics:thumbs_up")
                else:
                    self._redis.incr("rag:metrics:thumbs_down")
            except Exception as exc:
                logger.warning(f"Redis feedback caching error: {exc}")

        # 3. Active Learning: Mine hard negatives if thumbs down
        if request.rating == "thumbs_down":
            self._mine_hard_negatives_from_feedback(record)

        logger.info(f"Recorded feedback {rec_id}: rating={request.rating}, query='{request.query_text[:50]}'")
        return record

    def _mine_hard_negatives_from_feedback(self, record: FeedbackRecord) -> None:
        """Extracts hard negatives from citations associated with an unhelpful response."""
        for cit in record.citations:
            doc_id = cit.get("doc_id", "unknown")
            text = cit.get("text") or cit.get("snippet", "")
            score = float(cit.get("score") or cit.get("rerank_score", 0.0))
            if text:
                self.record_hard_negative(
                    query_text=record.query_text,
                    negative_doc_id=doc_id,
                    negative_text=text,
                    negative_score=score,
                    source="thumbs_down",
                )

    def record_hard_negative(
        self,
        query_text: str,
        negative_doc_id: str,
        negative_text: str,
        negative_score: float,
        source: str = "active_learning",
        positive_doc_id: str | None = None,
        positive_text: str | None = None,
    ) -> HardNegativeRecord:
        """Persists a single mined hard negative sample."""
        now_iso = datetime.now(timezone.utc).isoformat()
        sample_id = str(uuid.uuid4())
        sample = HardNegativeRecord(
            id=sample_id,
            timestamp=now_iso,
            query_text=query_text,
            positive_doc_id=positive_doc_id,
            positive_text=positive_text,
            negative_doc_id=negative_doc_id,
            negative_text=negative_text,
            negative_score=negative_score,
            source=source,
        )

        try:
            with open(self.hard_negatives_file, "a", encoding="utf-8") as f:
                f.write(sample.model_dump_json() + "\n")
        except Exception as exc:
            logger.error(f"Failed to append hard negative to disk: {exc}")

        if self._redis:
            try:
                self._redis.rpush("rag:hard_negatives:all", sample_id)
            except Exception:
                pass

        logger.info(f"Mined hard negative {sample_id} from source '{source}' for query='{query_text[:40]}'")
        return sample

    def get_summary(self) -> RAGOpsSummary:
        """Aggregates continuous evaluation metrics and feedback counters."""
        total = 0
        up = 0
        down = 0

        # Read from disk JSONL for accuracy
        if self.feedback_file.exists():
            try:
                with open(self.feedback_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            total += 1
                            if data.get("rating") == "thumbs_up":
                                up += 1
                            elif data.get("rating") == "thumbs_down":
                                down += 1
            except Exception as exc:
                logger.warning(f"Error reading feedback JSONL: {exc}")

        hn_count = 0
        if self.hard_negatives_file.exists():
            try:
                with open(self.hard_negatives_file, "r", encoding="utf-8") as f:
                    hn_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        satisfaction = round((up / total * 100), 1) if total > 0 else 0.0

        return RAGOpsSummary(
            total_feedback=total,
            thumbs_up=up,
            thumbs_down=down,
            satisfaction_rate_pct=satisfaction,
            hard_negatives_count=hn_count,
        )

    def export_training_dataset(self) -> list[dict[str, Any]]:
        """Exports mined contrastive samples in standardized format for model fine-tuning."""
        dataset: list[dict[str, Any]] = []
        if not self.hard_negatives_file.exists():
            return dataset

        try:
            with open(self.hard_negatives_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        dataset.append({
                            "query": rec.get("query_text"),
                            "positive": rec.get("positive_text") or "",
                            "negative": rec.get("negative_text"),
                            "negative_doc_id": rec.get("negative_doc_id"),
                            "negative_score": rec.get("negative_score"),
                            "source": rec.get("source"),
                            "timestamp": rec.get("timestamp"),
                        })
        except Exception as exc:
            logger.error(f"Error exporting training dataset: {exc}")

        return dataset
