"""Custom Reciprocal Rank Fusion (RRF) implementation for hybrid retrieval."""

from __future__ import annotations

from typing import Any

from contracts.retrieval import Candidate
from services.common.logger import get_logger

logger = get_logger("retrieval.rrf")


def reciprocal_rank_fusion(
    dense_results: list[tuple[dict[str, Any], float]],
    sparse_results: list[tuple[dict[str, Any], float]],
    k: int = 60,
    top_k: int = 20,
) -> list[Candidate]:
    """Combines dense and sparse ranked lists using Reciprocal Rank Fusion (RRF).

    Formula: RRF_score(d) = sum(1 / (k + rank_i(d)))
    """
    scores: dict[str, float] = {}
    dense_ranks: dict[str, int] = {}
    sparse_ranks: dict[str, int] = {}
    chunk_map: dict[str, dict[str, Any]] = {}

    # 1. Process Dense Results
    for rank_idx, (payload, _) in enumerate(dense_results):
        chunk_id = payload["id"]
        rank = rank_idx + 1  # 1-indexed
        dense_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        chunk_map[chunk_id] = payload

    # 2. Process Sparse Results
    for rank_idx, (payload, _) in enumerate(sparse_results):
        chunk_id = payload["id"]
        rank = rank_idx + 1  # 1-indexed
        sparse_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
        if chunk_id not in chunk_map:
            chunk_map[chunk_id] = payload

    # 3. Sort by RRF score descending
    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)[:top_k]

    # Theoretical maximum RRF score (rank 1 in both dense and sparse)
    max_possible_rrf = 2.0 / (k + 1)

    candidates: list[Candidate] = []
    for cid in sorted_ids:
        payload = chunk_map[cid]
        bbox_list = payload.get("bbox", [0.0, 0.0, 0.0, 0.0])
        bbox_tuple = (float(bbox_list[0]), float(bbox_list[1]), float(bbox_list[2]), float(bbox_list[3]))

        # Normalized RRF score mapped to [0.0, 1.0] scale
        norm_rrf = min(1.0, scores[cid] / max_possible_rrf)

        candidates.append(
            Candidate(
                id=cid,
                doc_id=payload.get("doc_id", ""),
                page=payload.get("page", 1),
                bbox=bbox_tuple,
                text=payload.get("text", ""),
                dense_rank=dense_ranks.get(cid),
                sparse_rank=sparse_ranks.get(cid),
                rrf_score=round(norm_rrf, 4),
                headings=payload.get("headings", []),
                is_table=payload.get("is_table", False),
                is_figure=payload.get("is_figure", False),
                image_path=payload.get("image_path"),
                caption=payload.get("caption"),
            )
        )

    logger.debug(f"RRF fused {len(dense_results)} dense and {len(sparse_results)} sparse into {len(candidates)} candidates")
    return candidates
