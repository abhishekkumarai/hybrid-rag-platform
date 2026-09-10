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

    @staticmethod
    def is_exploratory_or_summary_query(query: str) -> bool:
        """Detects broad, summary, or exploratory questions where cross-encoders under-score."""
        import re

        q = query.lower().strip()
        patterns = [
            r"\btell\s+me\s+about\b",
            r"\bwhat\s+(is|are)\s+(this|the|these)?\s*(document|file|paper|report|statement|pdf|passbook)\b",
            r"\bsummar(y|ize|ization|ising|ise)\b",
            r"\boverview\b",
            r"\bexplain\s+(this|the)?\s*(document|file)\b",
            r"\bwhat\s+does\s+(this|the)?\s*(document|file)\s+say\b",
            r"\bkey\s+(takeaways|points|findings)\b",
            r"\bwhat\s+is\s+in\s+(this|the)\s+(document|file)\b",
            r"\bdescribe\s+(this|the)?\s*(document|file)\b",
        ]
        return any(re.search(p, q) for p in patterns) or len(q.split()) <= 2

    def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        top_n: int = 6,
        min_score_cutoff: float | None = None,
    ) -> tuple[list[Candidate], list[Citation], bool]:
        """Reranks candidates and returns (top_candidates, citations, refused_flag)."""
        if not candidates:
            return [], [], True

        cutoff = min_score_cutoff if min_score_cutoff is not None else self.min_score_cutoff
        start = time.perf_counter()
        is_exploratory = self.is_exploratory_or_summary_query(query)

        if self.ranker:
            try:
                from flashrank import RerankRequest

                passages = [{"id": c.id, "text": c.text} for c in candidates]
                req = RerankRequest(query=query, passages=passages)
                results = self.ranker.rerank(req)

                score_map = {r["id"]: float(r["score"]) for r in results}
                for c in candidates:
                    raw_score = score_map.get(c.id, 0.0)
                    if is_exploratory or raw_score < 0.05:
                        # Calibrate score with normalized RRF score so exploratory queries aren't falsely refused
                        calibrated = max(raw_score, (c.rrf_score or 0.0) * 0.75)
                        c.rerank_score = round(calibrated, 4)
                    else:
                        c.rerank_score = round(raw_score, 4)

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
        refused = top_score < cutoff
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
