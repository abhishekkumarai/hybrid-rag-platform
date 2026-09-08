"""Langflow custom component for hybrid retrieval (Qdrant + BM25s + FlashRank)."""

from __future__ import annotations

from typing import Any

from contracts.retrieval import SearchQuery
from services.common.logger import get_logger
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.service import RetrievalService

logger = get_logger("components.retriever")

try:
    from langflow.custom import Component
    from langflow.io import FloatInput, IntInput, Output, StrInput
    _HAS_LANGFLOW = True
except ImportError:
    _HAS_LANGFLOW = False
    Component = object  # type: ignore


class HybridRetrieverComponent(Component):
    display_name = "Hybrid Retriever (HNSW + BM25s + RRF)"
    description = "Parallel dense Qdrant & sparse BM25s search, RRF (k=60), and FlashRank reranker."
    icon = "search-check"
    beta = True

    if _HAS_LANGFLOW:
        inputs = [
            StrInput(name="query", display_name="Search Query", required=True),
            IntInput(name="top_k", display_name="Top Candidates", value=20),
            IntInput(name="top_rerank", display_name="Top Rerank Passages", value=6),
            FloatInput(name="min_score_cutoff", display_name="Cutoff Refusal Score", value=0.15),
        ]
        outputs = [
            Output(name="context_text", display_name="Context Text", method="get_context"),
            Output(name="citations", display_name="Citations List", method="get_citations"),
            Output(name="refused", display_name="Refusal Flag", method="get_refused"),
        ]

    def __init__(self, **kwargs: Any) -> None:
        if _HAS_LANGFLOW:
            super().__init__(**kwargs)
        self.qdrant = QdrantStore(in_memory=False)
        self.bm25 = BM25Store()
        self.service = RetrievalService(qdrant_store=self.qdrant, bm25_store=self.bm25)

    def _execute(self, query: str, top_k: int = 20, top_rerank: int = 6, min_cutoff: float = 0.15) -> Any:
        req = SearchQuery(query_text=query, top_k=top_k, top_rerank=top_rerank, min_rerank_score=min_cutoff)
        return self.service.retrieve(req)

    def get_context(self, query: str, top_k: int = 20, top_rerank: int = 6, min_cutoff: float = 0.15) -> str:
        res = self._execute(query, top_k, top_rerank, min_cutoff)
        if res.refused:
            return "NO_RELEVANT_CONTEXT: The retrieved passages do not meet the minimum confidence threshold."
        passages = [f"--- Passage [{c.id}] (Page {c.page}) ---\n{c.text}" for c in res.candidates]
        return "\n\n".join(passages)

    def get_citations(self, query: str, top_k: int = 20, top_rerank: int = 6, min_cutoff: float = 0.15) -> list[dict[str, Any]]:
        res = self._execute(query, top_k, top_rerank, min_cutoff)
        return [c.model_dump() for c in res.citations]

    def get_refused(self, query: str, top_k: int = 20, top_rerank: int = 6, min_cutoff: float = 0.15) -> bool:
        res = self._execute(query, top_k, top_rerank, min_cutoff)
        return res.refused
