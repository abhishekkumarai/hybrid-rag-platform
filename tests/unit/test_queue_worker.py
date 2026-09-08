"""Unit tests for the Redis Task Queue, Ingestion Worker, and DLQ Manager."""

from __future__ import annotations

from unittest.mock import MagicMock

from contracts.document import Block, DocumentProfile, IngestResponse
from services.scheduler.dlq_manager import DLQManager
from services.scheduler.queue import (
    DLQ_QUEUE,
    PENDING_QUEUE,
    PROCESSING_QUEUE,
    IngestionJob,
    RedisTaskQueue,
)
from services.scheduler.worker import IngestionWorker


class MockRedisPipeline:
    def __init__(self, client: MockRedisClient):
        self.client = client
        self.commands: list[tuple[str, tuple]] = []

    def set(self, key: str, value: str) -> MockRedisPipeline:
        self.commands.append(("set", (key, value)))
        return self

    def lpush(self, key: str, value: str) -> MockRedisPipeline:
        self.commands.append(("lpush", (key, value)))
        return self

    def llen(self, key: str) -> MockRedisPipeline:
        self.commands.append(("llen", (key,)))
        return self

    def execute(self) -> list:
        results = []
        for cmd, args in self.commands:
            if cmd == "set":
                results.append(self.client.set(*args))
            elif cmd == "lpush":
                results.append(self.client.lpush(*args))
            elif cmd == "llen":
                results.append(self.client.llen(*args))
        self.commands = []
        return results


class MockRedisClient:
    """Deterministic in-memory mock simulating Redis list and key operations."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    def exists(self, key: str) -> int:
        return 1 if (key in self.kv or key in self.lists) else 0

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.kv[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.kv.get(key)

    def lpush(self, key: str, value: str) -> int:
        lst = self.lists.setdefault(key, [])
        lst.insert(0, value)
        return len(lst)

    def rpop(self, key: str) -> str | None:
        lst = self.lists.get(key, [])
        if lst:
            return lst.pop()
        return None

    def blmove(self, first_list: str, second_list: str, timeout: int, src: str, dest: str) -> str | None:
        src_lst = self.lists.get(first_list, [])
        if not src_lst:
            return None
        val = src_lst.pop()
        dest_lst = self.lists.setdefault(second_list, [])
        dest_lst.insert(0, val)
        return val

    def lrem(self, key: str, count: int, value: str) -> int:
        lst = self.lists.get(key, [])
        removed = 0
        while value in lst and (count == 0 or removed < count):
            lst.remove(value)
            removed += 1
        return removed

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        lst = self.lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]

    def delete(self, key: str) -> int:
        removed = 0
        if key in self.kv:
            del self.kv[key]
            removed += 1
        if key in self.lists:
            del self.lists[key]
            removed += 1
        return removed

    def pipeline(self) -> MockRedisPipeline:
        return MockRedisPipeline(self)


def test_redis_queue_enqueue_and_deduplication():
    mock_redis = MockRedisClient()
    queue = RedisTaskQueue(redis_client=mock_redis)

    # First enqueue succeeds
    task_id1 = queue.enqueue("doc1.pdf", "hash_abc_123")
    assert task_id1 is not None
    assert queue.client.llen(PENDING_QUEUE) == 1

    # Duplicate hash is skipped
    task_id2 = queue.enqueue("doc1_copy.pdf", "hash_abc_123")
    assert task_id2 is None
    assert queue.client.llen(PENDING_QUEUE) == 1


def test_redis_queue_pop_and_complete():
    mock_redis = MockRedisClient()
    queue = RedisTaskQueue(redis_client=mock_redis)

    queue.enqueue("report.pdf", "hash_report_01")
    job = queue.pop_task(timeout=1)

    assert job is not None
    assert job.file_path == "report.pdf"
    assert queue.client.llen(PENDING_QUEUE) == 0
    assert queue.client.llen(PROCESSING_QUEUE) == 1

    queue.complete_task(job)
    assert queue.client.llen(PROCESSING_QUEUE) == 0


def test_redis_queue_dlq_on_max_retries():
    mock_redis = MockRedisClient()
    queue = RedisTaskQueue(redis_client=mock_redis)

    queue.enqueue("corrupt.pdf", "hash_corrupt")
    job = queue.pop_task(timeout=1)

    # Attempt 1 -> Re-queued to pending
    queue.fail_task(job, error_msg="Corrupt PDF header")
    assert queue.client.llen(PENDING_QUEUE) == 1
    assert queue.client.llen(DLQ_QUEUE) == 0

    # Attempt 2 -> Re-queued to pending
    job = queue.pop_task(timeout=1)
    queue.fail_task(job, error_msg="Corrupt PDF header")
    assert queue.client.llen(PENDING_QUEUE) == 1
    assert queue.client.llen(DLQ_QUEUE) == 0

    # Attempt 3 -> Reaches max_retries, moved to DLQ
    job = queue.pop_task(timeout=1)
    queue.fail_task(job, error_msg="Corrupt PDF header")
    assert queue.client.llen(PENDING_QUEUE) == 0
    assert queue.client.llen(DLQ_QUEUE) == 1

    stats = queue.get_stats()
    assert stats["pending"] == 0
    assert stats["processing"] == 0
    assert stats["dlq"] == 1


def test_dlq_manager_inspection_and_replay():
    mock_redis = MockRedisClient()
    queue = RedisTaskQueue(redis_client=mock_redis)
    dlq_mgr = DLQManager(queue=queue)

    job = IngestionJob(file_path="failed.pdf", file_hash="hash_fail", attempts=3, error="Syntax error")
    mock_redis.lpush(DLQ_QUEUE, job.model_dump_json())

    # List dead letters
    dead_letters = dlq_mgr.list_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["file_path"] == "failed.pdf"

    # Replay dead letter
    replayed = dlq_mgr.replay_task(job.task_id)
    assert replayed is True
    assert mock_redis.llen(DLQ_QUEUE) == 0
    assert mock_redis.llen(PENDING_QUEUE) == 1


def test_worker_process_one_success():
    mock_redis = MockRedisClient()
    queue = RedisTaskQueue(redis_client=mock_redis)
    mock_ingestion = MagicMock()
    mock_indexing = MagicMock()

    mock_ingestion.parse.return_value = IngestResponse(
        doc_id="test_doc",
        file_path="sample.pdf",
        blocks=[
            Block(
                id="b1",
                doc_id="test_doc",
                page=1,
                bbox=(0.0, 0.0, 10.0, 10.0),
                text="Hello world",
                type="text",
                order=0,
            )
        ],
        profile=DocumentProfile(
            route="fast_text",
            page_count=1,
            sample_pages=[1],
            text_coverage=0.9,
            chars_per_page=100.0,
            image_ratio=0.0,
            columns=1,
            table_score=0.0,
            reason="clean",
        ),
        duration_ms=10.0,
    )

    worker = IngestionWorker(
        queue=queue,
        ingestion_service=mock_ingestion,
        indexing_service=mock_indexing,
        worker_id="test_worker_1",
    )

    queue.enqueue("sample.pdf", "hash_sample")
    did_work = worker.process_one(timeout=1)

    assert did_work is True
    assert mock_ingestion.parse.called
    assert mock_indexing.chunk_and_index.called
    assert queue.client.llen(PROCESSING_QUEUE) == 0
    assert queue.client.llen(PENDING_QUEUE) == 0
    assert mock_redis.get("rag:workers:test_worker_1") == "alive"
