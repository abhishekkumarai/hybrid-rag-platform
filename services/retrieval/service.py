"""Hybrid Retrieval Service coordinating Qdrant, BM25s, RRF, and FlashRank."""

from __future__ import annotations

import time

from contracts.compactor import CompactedContext
from contracts.graph import GraphRAGResponse
from contracts.retrieval import Candidate, RetrieveResponse, SearchQuery
from services.common.logger import get_logger
from services.graph.store import GraphStore
from services.graph.traversal import GraphTraverser
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.compactor import ContextCompactor
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion

logger = get_logger("retrieval.service")


class RetrievalService:
    """Decoupled hybrid retrieval, cross-encoder reranking, graph traversal, and compaction service."""

    def __init__(
        self,
        qdrant_store: QdrantStore,
        bm25_store: BM25Store,
        reranker: FlashRankReranker | None = None,
        graph_store: GraphStore | None = None,
        compactor: ContextCompactor | None = None,
        ollama_url: str = "http://127.0.0.1:11434",
    ) -> None:
        self.qdrant = qdrant_store
        self.bm25 = bm25_store
        self.reranker = reranker or FlashRankReranker()
        self.graph_store = graph_store
        self.traverser = GraphTraverser(graph_store) if graph_store else None
        self.compactor = compactor or ContextCompactor()
        self.ollama_url = ollama_url

    def retrieve(self, request: SearchQuery) -> RetrieveResponse:
        start = time.perf_counter()
        query = request.query_text

        # 1. Parallel / Dual Search
        dense_results = self.qdrant.search(query, top_k=request.top_k, ollama_url=self.ollama_url)
        sparse_results = self.bm25.search(query, top_k=request.top_k)

        # Scoped document filtering (e.g., Session attached files)
        if request.doc_ids:
            doc_id_set = set(request.doc_ids)
            dense_results = [r for r in dense_results if r[0].get("doc_id") in doc_id_set]
            sparse_results = [r for r in sparse_results if r[0].get("doc_id") in doc_id_set]

        # 2. Reciprocal Rank Fusion (k=60)
        candidates = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=60,
            top_k=request.top_k,
        )
        if request.doc_ids:
            candidates = [c for c in candidates if c.doc_id in doc_id_set]

        # 3. FlashRank Cross-Encoder Reranking
        top_candidates, citations, refused = self.reranker.rerank(
            query=query,
            candidates=candidates,
            top_n=request.top_rerank,
        )

        top_score = top_candidates[0].rerank_score if top_candidates else 0.0
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            f"RetrievalService: query='{query}' -> {len(dense_results)} dense, "
            f"{len(sparse_results)} sparse -> {len(top_candidates)} reranked "
            f"(top_score={top_score:.4f}, refused={refused}) in {duration_ms:.2f}ms"
        )

        return RetrieveResponse(
            query=query,
            candidates=top_candidates,
            citations=citations,
            refused=refused,
            top_score=top_score,
            duration_ms=round(duration_ms, 2),
        )

    def retrieve_with_graph(
        self, request: SearchQuery, max_hops: int = 2
    ) -> tuple[RetrieveResponse, GraphRAGResponse | None]:
        """Performs hybrid retrieval along with relational knowledge graph traversal."""
        ret_res = self.retrieve(request)
        graph_res: GraphRAGResponse | None = None

        if self.traverser:
            graph_res = self.traverser.query_graph(request.query_text, max_hops=max_hops)

        return ret_res, graph_res

    def compact_results(
        self,
        query: str,
        candidates: list[Candidate],
        budget_tokens: int = 3072,
        deduplicate: bool = True,
        prune_tables: bool = True,
    ) -> CompactedContext:
        """Compresses candidate passages to respect the Ollama context envelope."""
        return self.compactor.compress_candidates(
            query=query,
            candidates=candidates,
            budget_tokens=budget_tokens,
            deduplicate=deduplicate,
            prune_tables=prune_tables,
        )

