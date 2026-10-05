"""Temporal activities for document discovery, parsing, and indexing.

Replaces services/scheduler's Redis-backed DirectoryReconciler + IngestionWorker: the directory
scan and the ingest/index steps are now Temporal activities, invoked by the workflows in
`services.scheduling.workflows` and retried by Temporal's own retry policy instead of the old
queue's manual attempts-counter.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from temporalio import activity

from contracts.document import Block, IngestRequest
from services.common.logger import get_logger
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.scheduling.registry import (
    DATA_DOCS_DIR,
    SEEN_REGISTRY_FILE,
    SUPPORTED_EXTENSIONS,
    load_registry,
    save_registry,
)

logger = get_logger("scheduling.activities")


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 hash of file content for reliable deduplication."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class IngestionActivities:
    """Bound to one Temporal worker process; owns the IngestionService/IndexingService singletons
    so every activity invocation reuses already-loaded parser/embedding/reranker models instead of
    reloading them per task (same singleton-per-process shape as the old IngestionWorker).

    Registered with the Temporal `Worker` as bound-method activities, run on a thread-pool executor
    (see `services.scheduling.worker`) since parsing/indexing are synchronous, CPU/IO-bound calls."""

    def __init__(
        self,
        watch_dir: Path | str = DATA_DOCS_DIR,
        registry_file: Path | str = SEEN_REGISTRY_FILE,
    ) -> None:
        self.watch_dir = Path(watch_dir)
        self.registry_file = Path(registry_file)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.ingestion = IngestionService()
        self.indexing = IndexingService()

    @activity.defn
    def scan_directory(self) -> list[dict[str, str]]:
        """Scans the watched directory for files not yet dispatched, claiming each one in the
        registry immediately so a concurrent/overlapping scan never dispatches it twice.

        Unlike the old reconciler (which only marked a file "seen" once dispatch *succeeded*, so a
        failing file was silently retried forever on the next 60s scan), this marks a file seen as
        soon as it's dispatched. A document whose DocumentIngestWorkflow exhausts its retries shows
        up as a Failed workflow (the DLQ-equivalent in the admin UI) for a deliberate manual replay,
        rather than being retried silently and indefinitely."""
        seen = load_registry(self.registry_file)
        discovered: list[dict[str, str]] = []
        for item in sorted(self.watch_dir.iterdir()):
            if not (item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS):
                continue
            file_hash = compute_file_sha256(item)
            if file_hash in seen:
                continue
            seen[file_hash] = str(item)
            discovered.append({"file_path": str(item), "file_hash": file_hash})

        if discovered:
            save_registry(seen, self.registry_file)
            logger.info(f"Directory scan discovered {len(discovered)} new document(s)")
        return discovered

    @activity.defn
    def ingest_document(self, file_path: str) -> dict[str, Any]:
        """Parses one document into layout blocks."""
        result = self.ingestion.parse(IngestRequest(file_path=file_path))
        if result.error:
            raise RuntimeError(result.error)
        return result.model_dump(mode="json")

    @activity.defn
    def index_document(self, doc_id: str, raw_blocks: list[dict[str, Any]]) -> dict[str, Any]:
        """Chunks and indexes a document's already-parsed blocks."""
        blocks = [Block.model_validate(b) for b in raw_blocks]
        result = self.indexing.chunk_and_index(doc_id=doc_id, blocks=blocks)
        return result.model_dump(mode="json")
