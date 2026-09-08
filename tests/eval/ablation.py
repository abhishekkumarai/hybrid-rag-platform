"""Automated ablation benchmark comparing Dense, Sparse, Hybrid RRF, and Reranking."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure workspace root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.chunk import Chunk
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion


def run_ablation(temp_dir: Path) -> dict[str, float]:
    """Runs ablation experiment on keyword and semantic query benchmarks."""
    qdrant = QdrantStore(in_memory=True, collection_name="eval_ablation")
    bm25 = BM25Store(index_dir=temp_dir / "bm25")
    reranker = FlashRankReranker()

    # Benchmark corpus
    chunks = [
        Chunk(
            id="c_hardware",
            doc_id="eval",
            page=1,
            page_end=1,
            bbox=(0, 0, 10, 10),
            text="The NVIDIA GeForce RTX 3050 Laptop GPU has 6GB GDDR6 VRAM and 2048 CUDA cores.",
            raw_text="The NVIDIA GeForce RTX 3050 Laptop GPU has 6GB GDDR6 VRAM and 2048 CUDA cores.",
            token_count=15,
        ),
        Chunk(
            id="c_database",
            doc_id="eval",
            page=2,
            page_end=2,
            bbox=(0, 0, 10, 10),
            text="PostgreSQL relational database handles transactions and metadata on port 5432.",
            raw_text="PostgreSQL relational database handles transactions and metadata on port 5432.",
            token_count=14,
        ),
        Chunk(
            id="c_network",
            doc_id="eval",
            page=3,
            page_end=3,
            bbox=(0, 0, 10, 10),
            text="Redis provides atomic BLMOVE task queue and caching capabilities on port 6379.",
            raw_text="Redis provides atomic BLMOVE task queue and caching capabilities on port 6379.",
            token_count=13,
        ),
    ]

    qdrant.index(chunks)
    bm25.index(chunks)

    # Test query pairs: (query, target_chunk_id)
    eval_queries = [
        ("NVIDIA GeForce RTX 3050 VRAM", "c_hardware"),
        ("relational transactions port 5432", "c_database"),
        ("atomic queue caching port 6379", "c_network"),
    ]

    scores = {"dense_top1": 0.0, "sparse_top1": 0.0, "hybrid_top1": 0.0, "rerank_top1": 0.0}

    for query, target_id in eval_queries:
        dense_res = qdrant.search(query, top_k=3)
        sparse_res = bm25.search(query, top_k=3)
        fused = reciprocal_rank_fusion(dense_res, sparse_res, k=60, top_k=3)
        reranked, _, _ = reranker.rerank(query, fused, top_n=3)

        if dense_res and dense_res[0][0]["id"] == target_id:
            scores["dense_top1"] += 1
        if sparse_res and sparse_res[0][0]["id"] == target_id:
            scores["sparse_top1"] += 1
        if fused and fused[0].id == target_id:
            scores["hybrid_top1"] += 1
        if reranked and reranked[0].id == target_id:
            scores["rerank_top1"] += 1

    total = len(eval_queries)
    return {k: round(v / total, 2) for k, v in scores.items()}


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        results = run_ablation(Path(td))
        print("Ablation Results:", results)
