"""Background ingest jobs (IRA-60).

Adding a source is parse -> index -> attach. Driven by the web client, that chain and its progress died
with the screen that started it. Here the gateway owns it: the route saves the upload and returns a job
at once, a small thread pool runs the steps, and every stage is recorded so any client can read it back.

Jobs live in Redis next to projects (in-memory fallback). A job still queued/running under a different
`runner_id` belongs to a gateway process that no longer exists, so it is reported failed rather than
spinning forever.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from contracts.ingest_job import IngestJob, JobKind
from services.common.logger import get_logger

logger = get_logger("ingestion.jobs")

_KEY = "rag:ingest_jobs"
_FINISHED_TTL_S = 24 * 3600
_MAX_PER_USER = 50
RUNNER_ID = uuid.uuid4().hex[:12]


class StageReporter:
    """Handed to a job's work function so it can publish what it is doing."""

    def __init__(self, store: IngestJobStore, job: IngestJob):
        self._store = store
        self.job = job

    def __call__(self, stage: str, **fields: Any) -> None:
        self.job = self._store.update(self.job.id, stage=stage, **fields) or self.job


class IngestJobStore:
    # The Redis client is fetched on each call so the store follows the session manager's connection.
    def __init__(self, redis_client: Callable[[], Any]):
        self._redis = redis_client
        self._memory: dict[str, IngestJob] = {}
        self._lock = threading.Lock()

    def _put(self, job: IngestJob) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.hset(_KEY, job.id, job.model_dump_json())
                return
            except Exception as exc:
                logger.error(f"Error saving ingest job {job.id}: {exc}")
        with self._lock:
            self._memory[job.id] = job

    def _all(self) -> list[IngestJob]:
        client = self._redis()
        if client is not None:
            try:
                return [IngestJob.model_validate_json(raw) for raw in client.hvals(_KEY)]
            except Exception as exc:
                logger.error(f"Error listing ingest jobs: {exc}")
        with self._lock:
            return list(self._memory.values())

    def create(self, *, user_id: str, session_id: str, kind: JobKind, source: str) -> IngestJob:
        now = time.time()
        job = IngestJob(
            id=f"job_{uuid.uuid4().hex[:12]}", user_id=user_id, session_id=session_id, kind=kind,
            source=source, runner_id=RUNNER_ID, created_at=now, updated_at=now,
        )
        self._put(job)
        return job

    def get(self, job_id: str) -> IngestJob | None:
        client = self._redis()
        if client is not None:
            try:
                raw = client.hget(_KEY, job_id)
                return self._settle(IngestJob.model_validate_json(raw)) if raw else None
            except Exception as exc:
                logger.error(f"Error reading ingest job {job_id}: {exc}")
        with self._lock:
            job = self._memory.get(job_id)
        return self._settle(job) if job else None

    def update(self, job_id: str, **fields: Any) -> IngestJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job = job.model_copy(update={**fields, "updated_at": time.time()})
        self._put(job)
        return job

    def _settle(self, job: IngestJob) -> IngestJob:
        """Fail a job whose gateway process is gone (a restart mid-parse)."""
        if job.status in ("queued", "running") and job.runner_id != RUNNER_ID:
            job = job.model_copy(update={
                "status": "failed", "stage": "Interrupted",
                "error": "The gateway restarted while this was in progress. Add the source again.",
                "updated_at": time.time(),
            })
            self._put(job)
        return job

    def list_for(self, user_id: str, session_id: str | None = None) -> list[IngestJob]:
        """The caller's jobs, newest first. Finished jobs are dropped after a day."""
        cutoff = time.time() - _FINISHED_TTL_S
        jobs = []
        for job in self._all():
            if job.user_id != user_id or (session_id and job.session_id != session_id):
                continue
            job = self._settle(job)
            if job.status in ("done", "failed") and job.updated_at < cutoff:
                self.delete(job.id)
                continue
            jobs.append(job)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:_MAX_PER_USER]

    def delete(self, job_id: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.hdel(_KEY, job_id)
            except Exception as exc:
                logger.error(f"Error deleting ingest job {job_id}: {exc}")
        with self._lock:
            self._memory.pop(job_id, None)


# What a job does: reports stages, returns (doc_id, block_count). Raises to fail the job.
JobWork = Callable[[StageReporter], tuple[str, int]]


class IngestJobRunner:
    def __init__(self, store: IngestJobStore, max_workers: int = 2):
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ingest-job")

    def submit(self, job: IngestJob, work: JobWork) -> None:
        self._pool.submit(self._run, job, work)

    def _run(self, job: IngestJob, work: JobWork) -> None:
        report = StageReporter(self.store, job)
        report("Starting", status="running")
        try:
            doc_id, blocks = work(report)
            self.store.update(job.id, status="done", stage="Ready", doc_id=doc_id, blocks=blocks, error=None)
            logger.info(f"Ingest job {job.id} done: {job.source} -> {doc_id} ({blocks} blocks)")
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
            logger.warning(f"Ingest job {job.id} failed: {job.source}: {detail}")
            self.store.update(job.id, status="failed", stage="Failed", error=str(detail))
