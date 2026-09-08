"""Dead-Letter Queue (DLQ) inspection, replay, and management utility."""

from __future__ import annotations

import json
from typing import Any

from services.common.logger import get_logger
from services.scheduler.queue import DLQ_QUEUE, PENDING_QUEUE, IngestionJob, RedisTaskQueue

logger = get_logger("scheduler.dlq")


class DLQManager:
    """Manages dead-letter queue inspection, manual intervention, and replay."""

    def __init__(self, queue: RedisTaskQueue | None = None) -> None:
        self.queue = queue or RedisTaskQueue()

    def list_dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        """Returns list of tasks currently sitting in the DLQ."""
        raw_items = self.queue.client.lrange(DLQ_QUEUE, 0, limit - 1)
        results = []
        for item in raw_items:
            try:
                results.append(json.loads(item))
            except Exception:
                pass
        return results

    def replay_task(self, task_id: str) -> bool:
        """Finds a dead-letter job by ID, resets attempt counter, and re-queues to pending."""
        raw_items = self.queue.client.lrange(DLQ_QUEUE, 0, -1)
        for raw in raw_items:
            try:
                data = json.loads(raw)
                if data.get("task_id") == task_id:
                    # Remove from DLQ
                    self.queue.client.lrem(DLQ_QUEUE, 1, raw)
                    # Reset attempt and requeue
                    job = IngestionJob(**data)
                    job.attempts = 0
                    job.error = None
                    self.queue.client.lpush(PENDING_QUEUE, job.model_dump_json())
                    logger.info(f"Replayed task {task_id} back to pending queue")
                    return True
            except Exception as e:
                logger.error(f"Error parsing DLQ item: {e}")
        return False

    def replay_all(self) -> int:
        """Replays all tasks in the DLQ back to the pending queue."""
        replayed = 0
        while True:
            raw = self.queue.client.rpop(DLQ_QUEUE)
            if not raw:
                break
            try:
                data = json.loads(raw)
                job = IngestionJob(**data)
                job.attempts = 0
                job.error = None
                self.queue.client.lpush(PENDING_QUEUE, job.model_dump_json())
                replayed += 1
            except Exception:
                pass
        logger.info(f"Replayed {replayed} dead-letter tasks")
        return replayed

    def purge_dlq(self) -> int:
        """Purges all dead-letter tasks."""
        count = self.queue.client.llen(DLQ_QUEUE)
        self.queue.client.delete(DLQ_QUEUE)
        logger.info(f"Purged {count} tasks from DLQ")
        return count
