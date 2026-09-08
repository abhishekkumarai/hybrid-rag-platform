"""Dispatcher sending unindexed documents to Langflow Webhook or IngestionService."""

from __future__ import annotations

from pathlib import Path

import requests

from contracts.document import IngestRequest
from services.common.logger import get_logger
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService

logger = get_logger("scheduler.dispatcher")


class IngestionDispatcher:
    """Dispatches new documents to Langflow Webhook or local IngestionService."""

    def __init__(
        self,
        langflow_url: str = "http://localhost:7860",
        flow_id: str | None = None,
        use_webhook: bool = False,
    ) -> None:
        self.langflow_url = langflow_url
        self.flow_id = flow_id
        self.use_webhook = use_webhook
        self.ingestion_service = IngestionService()
        self.indexing_service = IndexingService()

    def dispatch(self, file_path: Path, file_hash: str) -> bool:
        """Dispatches document for ingestion."""
        if self.use_webhook and self.flow_id:
            webhook_url = f"{self.langflow_url}/api/v1/webhook/{self.flow_id}"
            try:
                logger.info(f"Posting '{file_path.name}' to Langflow webhook {webhook_url}")
                res = requests.post(
                    webhook_url,
                    json={"file_path": str(file_path), "file_hash": file_hash},
                    timeout=10.0,
                )
                if res.status_code in (200, 201, 202):
                    logger.info(f"Webhook ingestion accepted for '{file_path.name}'")
                    return True
                else:
                    logger.warning(f"Webhook returned status {res.status_code}: {res.text}")
            except Exception as e:
                logger.warning(f"Webhook dispatch failed ({e}), falling back to local service")

        # Local fallback execution
        try:
            logger.info(f"Executing local ingestion pipeline for '{file_path.name}'")
            req = IngestRequest(file_path=str(file_path))
            ingest_res = self.ingestion_service.parse(req)
            self.indexing_service.chunk_and_index(doc_id=ingest_res.doc_id, blocks=ingest_res.blocks)
            logger.info(f"Local ingestion succeeded for '{file_path.name}' (doc_id={ingest_res.doc_id})")
            return True
        except Exception as e:
            logger.error(f"Local ingestion pipeline failed for '{file_path.name}': {e}")
            return False
