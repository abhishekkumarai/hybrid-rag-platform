"""Gateway-facing helpers for inspecting and replaying document-ingestion Temporal workflows.

Backs the same `/api/v1/queue/*` endpoints that used to read services/scheduler's Redis queue
(services/gateway/api.py), so the existing admin UI (Flutter's ObservabilityScreen and legacy
ui/index.html) needs no changes — same response shapes, same field names.

Replay doesn't walk Temporal's workflow history to recover a failed run's original arguments
(`file_path`/`file_hash`) — that needs decoding raw history-event payloads, which is finicky and
version-sensitive. Instead, `DocumentIngestWorkflow`'s id is always `ingest-{file_hash}` (see
`services.scheduling.workflows.ingest_workflow_id`), and the discovery registry already maps
`file_hash -> file_path` (it's written by the scan activity precisely to answer "have we seen this
file"). So replay just looks the hash up in that registry — no history introspection needed.
"""

from __future__ import annotations

import time
from typing import Any

from temporalio.client import Client, WorkflowExecutionStatus

from services.common.config import load_config
from services.common.logger import get_logger
from services.scheduling.registry import load_registry
from services.scheduling.workflows import TASK_QUEUE, DocumentIngestWorkflow, ingest_workflow_id

logger = get_logger("scheduling.client")

_FAILED_QUERY = "WorkflowType='DocumentIngestWorkflow' AND ExecutionStatus='Failed'"
_RUNNING_QUERY = "WorkflowType='DocumentIngestWorkflow' AND ExecutionStatus='Running'"

_client: Client | None = None


async def get_temporal_client() -> Client:
    """Lazily connects on first use so the gateway never blocks startup/health on Temporal being
    up — only the admin observability screen (which calls into this module) needs it reachable."""
    global _client
    if _client is None:
        s = load_config().scheduling
        target = f"{s.temporal_host}:{s.temporal_port}"
        _client = await Client.connect(target, namespace=s.temporal_namespace)
    return _client


def _file_hash_from_workflow_id(workflow_id: str) -> str:
    return workflow_id.removeprefix("ingest-")


async def queue_stats() -> dict[str, int]:
    """Running document-ingestion workflows ("processing") and failed ones ("dlq"). There's no
    Temporal equivalent of a "pending" depth (work is dispatched to a worker's task queue, not held
    in an inspectable backlog the way the old Redis list was), so it's always 0 — kept in the
    response only so the frontend's existing `Map<String, int>` shape doesn't need to change."""
    client = await get_temporal_client()
    processing = sum([1 async for _ in client.list_workflows(query=_RUNNING_QUERY)])
    dlq = sum([1 async for _ in client.list_workflows(query=_FAILED_QUERY)])
    return {"pending": 0, "processing": processing, "dlq": dlq}


async def list_dead_letters(limit: int = 50) -> list[dict[str, Any]]:
    """Lists failed document-ingestion workflows — the Temporal equivalent of the old DLQ."""
    client = await get_temporal_client()
    registry = load_registry()
    results: list[dict[str, Any]] = []
    async for wf in client.list_workflows(query=_FAILED_QUERY):
        if len(results) >= limit:
            break
        file_hash = _file_hash_from_workflow_id(wf.id)
        results.append({
            "task_id": wf.id,
            "id": wf.id,
            "file_path": registry.get(file_hash, "unknown"),
            "error": "Failed after exhausting Temporal retries — see the Temporal UI for details",
        })
    return results


async def replay_task(task_id: str) -> bool:
    """Restarts one failed workflow by its workflow id, re-dispatching the same `file_path` under a
    fresh run id. Returns False if the id isn't a known failed DocumentIngestWorkflow."""
    client = await get_temporal_client()
    try:
        description = await client.get_workflow_handle(task_id).describe()
    except Exception:
        return False
    if description.status != WorkflowExecutionStatus.FAILED:
        return False

    file_hash = _file_hash_from_workflow_id(task_id)
    file_path = load_registry().get(file_hash)
    if not file_path:
        logger.warning(f"No registry entry for failed workflow {task_id}; cannot replay")
        return False

    await client.start_workflow(
        DocumentIngestWorkflow.run,
        args=[file_path, file_hash],
        id=f"{ingest_workflow_id(file_hash)}-retry-{int(time.time())}",
        task_queue=TASK_QUEUE,
    )
    logger.info(f"Replayed failed workflow {task_id} for '{file_path}'")
    return True


async def replay_all() -> int:
    """Replays every currently-failed document-ingestion workflow. Returns how many were replayed."""
    client = await get_temporal_client()
    failed_ids = [wf.id async for wf in client.list_workflows(query=_FAILED_QUERY)]
    replayed = 0
    for workflow_id in failed_ids:
        if await replay_task(workflow_id):
            replayed += 1
    return replayed
