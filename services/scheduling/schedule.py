"""Provisions the recurring Temporal Schedule that replaces the old reconciler's 60s poll loop."""

from __future__ import annotations

from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleState,
)

from services.common.logger import get_logger
from services.scheduling.workflows import TASK_QUEUE, DirectoryScanWorkflow

logger = get_logger("scheduling.schedule")

DIRECTORY_SCAN_SCHEDULE_ID = "document-directory-scan"


async def ensure_directory_scan_schedule(client: Client, interval_sec: int = 60) -> None:
    """Idempotently creates the recurring directory-scan schedule. Safe to call on every worker
    startup: Temporal rejects a duplicate `create_schedule` by id, which is treated here as "already
    provisioned" rather than an error."""
    schedule = Schedule(
        action=ScheduleActionStartWorkflow(
            DirectoryScanWorkflow.run,
            id=f"{DIRECTORY_SCAN_SCHEDULE_ID}-run",
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=interval_sec))]),
        state=ScheduleState(paused=False),
    )
    try:
        await client.create_schedule(DIRECTORY_SCAN_SCHEDULE_ID, schedule)
        logger.info(f"Created Temporal schedule '{DIRECTORY_SCAN_SCHEDULE_ID}' (every {interval_sec}s)")
    except ScheduleAlreadyRunningError:
        logger.info(f"Temporal schedule '{DIRECTORY_SCAN_SCHEDULE_ID}' already exists")
    except Exception as e:
        if "already" in str(e).lower() or "ALREADY_EXISTS" in str(e):
            logger.info(f"Temporal schedule '{DIRECTORY_SCAN_SCHEDULE_ID}' already exists")
        else:
            raise
