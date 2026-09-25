"""Hybrid Retrieval Service coordinating Qdrant, BM25s, RRF, and FlashRank."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from contracts.compactor import CompactedContext
from contracts.graph import GraphRAGResponse
from contracts.retrieval import Candidate, RetrieveResponse, SearchQuery
from services.common.doc_scope import matches_doc_scope
from services.common.logger import get_logger
from services.graph.store import GraphStore
from services.graph.traversal import GraphTraverser
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.compactor import ContextCompactor
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion

T = TypeVar("T")

logger = get_logger("retrieval.service")

# Shared across requests: each retrieval uses two workers (dense + sparse), so 8 serves 4 at once.
_SEARCH_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="hybrid-search")


def _timed(fn: Callable[..., T], *args: Any, **kwargs: Any) -> tuple[T, float]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000


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
        is_exploratory_query = FlashRankReranker.is_exploratory_or_summary_query(query)

        # Scoped document pre-resolution
        resolved_doc_ids = (
            self.bm25.resolve_matching_doc_ids(request.doc_ids) if request.doc_ids else None
        )
        doc_id_set = set(resolved_doc_ids) if resolved_doc_ids else None

        # 1. Concurrent dual search with pre-filtering. Dense waits on an Ollama embedding
        # round-trip while BM25 is pure CPU, so overlapping them hides most of the sparse cost.
        dense_future = _SEARCH_POOL.submit(
            _timed,
            self.qdrant.search,
            query,
            top_k=request.top_k,
            ollama_url=self.ollama_url,
            doc_ids=resolved_doc_ids,
            ef_search=request.ef_search,
        )
        sparse_future = _SEARCH_POOL.submit(
            _timed,
            self.bm25.search,
            query,
            top_k=request.top_k,
            doc_ids=resolved_doc_ids,
        )
        dense_results, dense_ms = dense_future.result()
        sparse_results, sparse_ms = sparse_future.result()

        # Scoped document filtering safeguard
        if doc_id_set:
            dense_results = [r for r in dense_results if matches_doc_scope(r[0].get("doc_id"), doc_id_set)]
            sparse_results = [r for r in sparse_results if matches_doc_scope(r[0].get("doc_id"), doc_id_set)]

        # 2. Reciprocal Rank Fusion (k=60)
        candidates = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=60,
            top_k=request.top_k,
        )
        if doc_id_set:
            candidates = [c for c in candidates if matches_doc_scope(c.doc_id, doc_id_set)]

            # If candidates are empty or query is exploratory/summary, anchor with document overview chunks
            if not candidates or is_exploratory_query:
                overview_chunks = self.bm25.get_document_overview_chunks(list(doc_id_set), max_chunks=3)
                existing_cids = {c.id for c in candidates}
                for ch in overview_chunks:
                    if ch.get("id") not in existing_cids:
                        b_list = ch.get("bbox", [0.0, 0.0, 0.0, 0.0])
                        candidates.append(
                            Candidate(
                                id=ch["id"],
                                doc_id=ch.get("doc_id", ""),
                                page=ch.get("page", 1),
                                bbox=(float(b_list[0]), float(b_list[1]), float(b_list[2]), float(b_list[3])),
                                text=ch.get("text", ""),
                                rrf_score=0.85,
                                headings=ch.get("headings", []),
                                is_table=ch.get("is_table", False),
                            )
                        )

        # 3. FlashRank Cross-Encoder Reranking
        effective_cutoff = (
            min(request.min_rerank_score, 0.05)
            if (request.doc_ids and is_exploratory_query)
            else request.min_rerank_score
        )

        top_candidates, citations, refused = self.reranker.rerank(
            query=query,
            candidates=candidates,
            top_n=request.top_rerank,
            min_score_cutoff=effective_cutoff,
        )

        top_score = top_candidates[0].rerank_score if top_candidates else 0.0
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            f"RetrievalService: query='{query}' -> {len(dense_results)} dense, "
            f"{len(sparse_results)} sparse (dense={dense_ms:.1f}ms, sparse={sparse_ms:.1f}ms) -> "
            f"{len(top_candidates)} reranked "
            f"(top_score={top_score:.4f}, refused={refused}) in {duration_ms:.2f}ms"
        )

        return RetrieveResponse(
            query=query,
            candidates=top_candidates,
            citations=citations,
            refused=refused,
            top_score=top_score,
            reranker_degraded=self.reranker.last_call_degraded,
            duration_ms=round(duration_ms, 2),
        )

    def retrieve_with_graph(
        self, request: SearchQuery, max_hops: int = 2
    ) -> tuple[RetrieveResponse, GraphRAGResponse | None]:
        """Performs hybrid retrieval along with relational knowledge graph traversal."""
        ret_res = self.retrieve(request)
        graph_res: GraphRAGResponse | None = None

        if self.traverser:
            graph_res = self.traverser.query_graph(
                request.query_text, max_hops=max_hops, doc_ids=request.doc_ids
            )

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

