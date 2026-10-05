"""Temporal worker entrypoint: registers workflows/activities, provisions the recurring
directory-scan schedule, and runs the task queue consumer.

Replaces services/scheduler/worker.py (Redis queue consumer) and services/scheduler/reconciler.py
(directory-scan daemon) with a single Temporal worker process."""

from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.client import Client
from temporalio.worker import Worker

from services.common.config import load_config
from services.common.logger import get_logger
from services.scheduling.activities import IngestionActivities
from services.scheduling.schedule import ensure_directory_scan_schedule
from services.scheduling.workflows import TASK_QUEUE, DirectoryScanWorkflow, DocumentIngestWorkflow

logger = get_logger("scheduling.worker")


async def main() -> None:
    config = load_config()
    s = config.scheduling
    target = f"{s.temporal_host}:{s.temporal_port}"
    client = await Client.connect(target, namespace=s.temporal_namespace)
    logger.info(f"Connected to Temporal at {target} (namespace={s.temporal_namespace})")

    await ensure_directory_scan_schedule(client, interval_sec=s.scan_interval_s)

    activities = IngestionActivities()
    # ingest_document/index_document are synchronous (parsing and embedding are CPU/IO-bound, not
    # asyncio-friendly), so they run on a thread-pool executor rather than the worker's event loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as activity_executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[DirectoryScanWorkflow, DocumentIngestWorkflow],
            activities=[
                activities.scan_directory,
                activities.ingest_document,
                activities.index_document,
            ],
            activity_executor=activity_executor,
        )
        logger.info(f"Starting Temporal worker on task queue '{TASK_QUEUE}'")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
