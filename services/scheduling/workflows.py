"""Temporal workflows orchestrating document discovery, parsing, and indexing."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from services.scheduling.activities import IngestionActivities

TASK_QUEUE = "document-ingestion"

# Matches the old Redis queue's `max_retries=3` (services/scheduler/queue.py), now enforced per
# activity by Temporal itself instead of a manual attempts counter.
INGEST_RETRY_POLICY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))


@workflow.defn
class DocumentIngestWorkflow:
    """Parses and indexes one document. Its workflow id is `ingest-{file_hash}` (full hash, not
    truncated) so the gateway's DLQ replay endpoint can recover the original `file_path` from the
    id alone via the discovery registry — see `services.scheduling.client`."""

    @workflow.run
    async def run(self, file_path: str, file_hash: str) -> dict[str, Any]:
        ingest_result = await workflow.execute_activity_method(
            IngestionActivities.ingest_document,
            file_path,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=INGEST_RETRY_POLICY,
        )
        index_result = await workflow.execute_activity_method(
            IngestionActivities.index_document,
            args=[ingest_result["doc_id"], ingest_result["blocks"]],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=INGEST_RETRY_POLICY,
        )
        return index_result


def ingest_workflow_id(file_hash: str) -> str:
    """The deterministic workflow id `DocumentIngestWorkflow` runs under for a given file hash —
    shared by the scan workflow (starting it) and the gateway's replay endpoint (restarting it)."""
    return f"ingest-{file_hash}"


@workflow.defn
class DirectoryScanWorkflow:
    """Replaces the old `DirectoryReconciler` daemon (services/scheduler/reconciler.py): scans
    data/documents/ for undispatched files and fans each one out to its own
    `DocumentIngestWorkflow`, run on a recurring Temporal Schedule (see
    `services.scheduling.schedule`) instead of a 60s `time.sleep` loop.

    Each discovered file gets its own child workflow (fire-and-forget, `ParentClosePolicy.ABANDON`)
    so one file's exhausted retries never block or delay the rest, and each file's status is
    independently visible and replayable in the Temporal UI / admin DLQ view."""

    @workflow.run
    async def run(self) -> dict[str, int]:
        discovered = await workflow.execute_activity_method(
            IngestionActivities.scan_directory,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        for doc in discovered:
            await workflow.start_child_workflow(
                DocumentIngestWorkflow.run,
                args=[doc["file_path"], doc["file_hash"]],
                id=ingest_workflow_id(doc["file_hash"]),
                task_queue=TASK_QUEUE,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
        return {"discovered": len(discovered)}
