"""Redis Task Queue with atomic transactions and Dead-Letter Queue (DLQ) support."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from services.common.config import load_config
from services.common.logger import get_logger

logger = get_logger("scheduler.queue")
config = load_config()

PENDING_QUEUE = "rag:queue:pending"
PROCESSING_QUEUE = "rag:queue:processing"
DLQ_QUEUE = "rag:queue:dlq"
SEEN_PREFIX = "rag:tasks:seen:"


class IngestionJob(BaseModel):
    """Payload representing an asynchronous document ingestion job."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_path: str
    file_hash: str
    attempts: int = 0
    max_retries: int = 3
    created_at: float = Field(default_factory=time.time)
    error: str | None = None


class RedisTaskQueue:
    """Manages atomic Redis queue operations, deduplication, and DLQ routing."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.host = host or config.storage.redis_host
        self.port = port or config.storage.redis_port

        if redis_client is not None:
            self.client = redis_client
        else:
            import redis
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
                socket_timeout=5.0,
            )

    def enqueue(self, file_path: Path | str, file_hash: str, force: bool = False) -> str | None:
        """Atomically pushes job to pending queue if file_hash has not been seen."""
        seen_key = f"{SEEN_PREFIX}{file_hash}"
        if not force and self.client.exists(seen_key):
            logger.info(f"Task for hash '{file_hash[:10]}' already queued or completed. Skipping.")
            return None

        job = IngestionJob(file_path=str(file_path), file_hash=file_hash)
        payload = job.model_dump_json()

        # Atomic pipeline: mark seen and push to pending
        pipe = self.client.pipeline()
        pipe.set(seen_key, job.task_id)
        pipe.lpush(PENDING_QUEUE, payload)
        pipe.execute()

        logger.info(f"Enqueued job {job.task_id} for '{Path(file_path).name}' (pending)")
        return job.task_id

    def pop_task(self, timeout: int = 2) -> IngestionJob | None:
        """Atomically pops from pending queue and moves into processing queue."""
        raw_payload = None
        try:
            # BLMOVE is available in Redis >= 6.2; fallback to BRPOPLPUSH if needed
            if hasattr(self.client, "blmove"):
                raw_payload = self.client.blmove(
                    first_list=PENDING_QUEUE,
                    second_list=PROCESSING_QUEUE,
                    timeout=timeout,
                    src="RIGHT",
                    dest="LEFT",
                )
            else:
                raw_payload = self.client.brpoplpush(
                    src=PENDING_QUEUE,
                    dst=PROCESSING_QUEUE,
                    timeout=timeout,
                )
        except Exception as e:
            logger.error(f"Error popping task from Redis queue: {e}")
            return None

        if not raw_payload:
            return None

        data = json.loads(raw_payload)
        return IngestionJob(**data)

    def complete_task(self, job: IngestionJob) -> None:
        """Removes job from processing queue upon successful completion."""
        self.client.lrem(PROCESSING_QUEUE, count=1, value=job.model_dump_json())
        logger.info(f"Completed task {job.task_id} for '{Path(job.file_path).name}'")

    def fail_task(self, job: IngestionJob, error_msg: str) -> None:
        """Increments attempt count; re-queues if attempts < max_retries, else moves to DLQ."""
        # 1. Remove from processing
        self.client.lrem(PROCESSING_QUEUE, count=1, value=job.model_dump_json())

        # 2. Update job
        job.attempts += 1
        job.error = error_msg

        if job.attempts >= job.max_retries:
            # Dead-Letter Queue
            logger.warning(
                f"Task {job.task_id} failed {job.attempts}/{job.max_retries} times. Moving to DLQ: {error_msg}"
            )
            self.client.lpush(DLQ_QUEUE, job.model_dump_json())
        else:
            # Retry: Push back to pending
            logger.info(
                f"Task {job.task_id} failed (attempt {job.attempts}/{job.max_retries}). Retrying in pending queue..."
            )
            self.client.lpush(PENDING_QUEUE, job.model_dump_json())

    def get_stats(self) -> dict[str, int]:
        """Returns length of pending, processing, and dead-letter queues."""
        try:
            pipe = self.client.pipeline()
            pipe.llen(PENDING_QUEUE)
            pipe.llen(PROCESSING_QUEUE)
            pipe.llen(DLQ_QUEUE)
            pending, processing, dlq = pipe.execute()
            return {"pending": pending, "processing": processing, "dlq": dlq}
        except Exception:
            return {"pending": 0, "processing": 0, "dlq": 0}
