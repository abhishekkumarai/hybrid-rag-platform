"""Langflow custom component for hierarchical chunking and dual storage."""

from __future__ import annotations

from typing import Any

from contracts.document import Block
from services.common.logger import get_logger
from services.indexing.service import IndexingService

logger = get_logger("components.chunker")

try:
    from langflow.custom import Component
    from langflow.io import DataInput, IntInput, Output, StrInput
    _HAS_LANGFLOW = True
except ImportError:
    _HAS_LANGFLOW = False
    Component = object  # type: ignore


class ContentAwareChunkerComponent(Component):
    display_name = "Content-Aware Chunker & Indexer"
    description = "Preserves tables, section breadcrumbs, enforces 512-token cap, and indexes to Qdrant + BM25s."
    icon = "split"
    beta = True

    if _HAS_LANGFLOW:
        inputs = [
            DataInput(name="blocks_data", display_name="Blocks Data", info="Extracted blocks from Layout Probe"),
            StrInput(name="doc_id", display_name="Document ID", value="doc"),
            IntInput(name="max_tokens", display_name="Max Tokens", value=512),
        ]
        outputs = [
            Output(name="index_status", display_name="Index Status", method="index_blocks"),
        ]

    def __init__(self, **kwargs: Any) -> None:
        if _HAS_LANGFLOW:
            super().__init__(**kwargs)
        self.service = IndexingService(in_memory=False)

    def index_blocks(self, blocks_data: list[dict[str, Any]], doc_id: str = "doc") -> dict[str, Any]:
        blocks = [Block(**b) for b in blocks_data]
        res = self.service.chunk_and_index(doc_id=doc_id, blocks=blocks)
        return res.model_dump()
