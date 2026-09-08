"""Worker daemon processing asynchronous ingestion jobs from Redis."""

from __future__ import annotations

import signal
import time
import uuid
from pathlib import Path

from contracts.document import IngestRequest
from services.common.logger import get_logger
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.scheduler.queue import RedisTaskQueue

logger = get_logger("scheduler.worker")


class IngestionWorker:
    """Consumes tasks from Redis queue and processes them through ingestion and indexing."""

    def __init__(
        self,
        queue: RedisTaskQueue | None = None,
        ingestion_service: IngestionService | None = None,
        indexing_service: IndexingService | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.queue = queue or RedisTaskQueue()
        self.ingestion = ingestion_service or IngestionService()
        self.indexing = indexing_service or IndexingService()
        self._running = True

    def send_heartbeat(self) -> None:
        """Emits worker heartbeat in Redis with 10-second TTL."""
        try:
            self.queue.client.set(f"rag:workers:{self.worker_id}", "alive", ex=10)
        except Exception:
            pass

    def process_one(self, timeout: int = 2) -> bool:
        """Pops and processes a single task. Returns True if a task was processed, False if timed out."""
        self.send_heartbeat()
        job = self.queue.pop_task(timeout=timeout)
        if not job:
            return False

        logger.info(f"[{self.worker_id}] Processing task {job.task_id}: '{Path(job.file_path).name}'")
        try:
            # 1. Parse layout blocks
            ingest_req = IngestRequest(file_path=job.file_path)
            ingest_res = self.ingestion.parse(ingest_req)

            # 2. Chunk and index
            self.indexing.chunk_and_index(doc_id=ingest_res.doc_id, blocks=ingest_res.blocks)

            # 3. Mark complete
            self.queue.complete_task(job)
            logger.info(f"[{self.worker_id}] Successfully finished task {job.task_id}")
            return True

        except Exception as e:
            logger.error(f"[{self.worker_id}] Task {job.task_id} failed: {e}")
            self.queue.fail_task(job, error_msg=str(e))
            return True

    def run_forever(self, poll_interval: float = 1.0) -> None:
        """Main daemon loop."""
        logger.info(f"Starting IngestionWorker [{self.worker_id}]...")

        def _handle_signal(sig, frame):
            logger.info(f"[{self.worker_id}] Shutting down gracefully...")
            self._running = False

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            pass

        while self._running:
            did_work = self.process_one(timeout=2)
            if not did_work:
                time.sleep(poll_interval)


if __name__ == "__main__":
    worker = IngestionWorker()
    worker.run_forever()
