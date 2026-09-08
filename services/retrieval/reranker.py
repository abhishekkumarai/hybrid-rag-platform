"""FlashRank CPU cross-encoder reranker with score cutoff refusal."""

from __future__ import annotations

import time
from typing import Any

from contracts.retrieval import Candidate, Citation
from services.common.logger import get_logger

logger = get_logger("retrieval.reranker")


class FlashRankReranker:
    """Local CPU-based cross-encoder reranker using FlashRank."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2", min_score_cutoff: float = 0.15) -> None:
        self.model_name = model_name
        self.min_score_cutoff = min_score_cutoff
        self.ranker: Any = None
        self._init_ranker()

    def _init_ranker(self) -> None:
        try:
            from flashrank import Ranker
            self.ranker = Ranker(model_name=self.model_name)
            logger.info(f"Initialized FlashRank with model '{self.model_name}' on CPU")
        except Exception as e:
            logger.warning(f"Could not load FlashRank ({e}); fallback ranking will be used")
            self.ranker = None

    def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        top_n: int = 6,
    ) -> tuple[list[Candidate], list[Citation], bool]:
        """Reranks candidates and returns (top_candidates, citations, refused_flag)."""
        if not candidates:
            return [], [], True

        start = time.perf_counter()

        if self.ranker:
            try:
                from flashrank import RerankRequest

                passages = [{"id": c.id, "text": c.text} for c in candidates]
                req = RerankRequest(query=query, passages=passages)
                results = self.ranker.rerank(req)

                score_map = {r["id"]: float(r["score"]) for r in results}
                for c in candidates:
                    c.rerank_score = round(score_map.get(c.id, 0.0), 4)

                # Sort by rerank score descending
                candidates.sort(key=lambda x: x.rerank_score, reverse=True)
            except Exception as e:
                logger.warning(f"FlashRank reranking failed ({e}), using RRF scores as fallback")
                for c in candidates:
                    c.rerank_score = c.rrf_score
        else:
            # Fallback: RRF score normalized
            for c in candidates:
                c.rerank_score = c.rrf_score

        top_candidates = candidates[:top_n]
        top_score = top_candidates[0].rerank_score if top_candidates else 0.0

        # Refusal Cutoff Check
        refused = top_score < self.min_score_cutoff
        duration_ms = (time.perf_counter() - start) * 1000

        # Generate citations
        citations: list[Citation] = []
        for c in top_candidates:
            b = c.bbox
            formatted_badge = f"[{c.doc_id}: Page {c.page}, ({b[0]:.1f}, {b[1]:.1f}, {b[2]:.1f}, {b[3]:.1f})]"
            citations.append(
                Citation(
                    doc_id=c.doc_id,
                    page=c.page,
                    bbox=c.bbox,
                    snippet=c.text[:150] + ("..." if len(c.text) > 150 else ""),
                    formatted_badge=formatted_badge,
                    is_table=c.is_table,
                    is_figure=c.is_figure,
                    image_path=c.image_path,
                )
            )

        logger.info(
            f"Reranking completed in {duration_ms:.2f}ms: top_score={top_score:.4f}, "
            f"cutoff={self.min_score_cutoff}, refused={refused}"
        )

        return top_candidates, citations, refused
