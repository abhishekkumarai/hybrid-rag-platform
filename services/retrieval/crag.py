"""Corrective RAG (CRAG) Evaluator & Reformulator for Phase 12."""

import re
from typing import Sequence

from contracts.agent import CRAGAssessment
from contracts.retrieval import Candidate
from services.common.logger import get_logger

logger = get_logger("crag_evaluator")

STOP_WORDS = {
    "what", "is", "the", "are", "and", "or", "in", "on", "of", "for", "with",
    "about", "to", "a", "an", "at", "by", "from", "how", "why", "where", "which",
    "can", "you", "tell", "me", "show", "describe", "explain"
}


class CRAGEvaluator:
    """Evaluates candidate relevance confidence and generates corrective query reformulations."""

    def __init__(
        self,
        confident_threshold: float = 0.45,
        refusal_threshold: float = 0.15,
    ) -> None:
        self.confident_threshold = confident_threshold
        self.refusal_threshold = refusal_threshold

    def evaluate(self, query: str, candidates: Sequence[Candidate]) -> CRAGAssessment:
        """Assesses retrieval quality across top cross-encoder scores and keyword alignment."""
        if not candidates:
            return CRAGAssessment(
                status="REFUSE",
                top_score=0.0,
                reformulated_query=None,
                reason="No candidate documents retrieved",
            )

        from services.retrieval.reranker import FlashRankReranker

        top_score = max((c.rerank_score if c.rerank_score > 0 else c.rrf_score for c in candidates), default=0.0)
        is_exploratory = FlashRankReranker.is_exploratory_or_summary_query(query)

        # 1. Check refusal threshold (with adaptive floor for exploratory queries)
        effective_threshold = 0.05 if is_exploratory else self.refusal_threshold
        if top_score < effective_threshold:
            logger.info(f"CRAG Refusal: top score {top_score:.4f} < {effective_threshold}")
            return CRAGAssessment(
                status="REFUSE",
                top_score=round(top_score, 4),
                reformulated_query=None,
                reason=f"Top candidate score ({top_score:.4f}) fell below confidence floor ({effective_threshold})",
            )

        if is_exploratory:
            logger.info(f"CRAG Confident (Exploratory): top score {top_score:.4f} for broad document query")
            return CRAGAssessment(
                status="CONFIDENT",
                top_score=round(top_score, 4),
                reformulated_query=None,
                reason="Exploratory document query with grounded document candidates",
            )

        # 2. Check keyword alignment
        query_words = [
            w.lower() for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", query)
            if w.lower() not in STOP_WORDS
        ]
        top_text = " ".join([c.text.lower() for c in candidates[:3]])
        matched_words = [w for w in query_words if w in top_text]
        keyword_overlap_ratio = len(matched_words) / len(query_words) if query_words else 1.0

        # 3. Confident evaluation
        if top_score >= self.confident_threshold and keyword_overlap_ratio >= 0.5:
            logger.info(f"CRAG Confident: top score {top_score:.4f}, keyword overlap {keyword_overlap_ratio:.2f}")
            return CRAGAssessment(
                status="CONFIDENT",
                top_score=round(top_score, 4),
                reformulated_query=None,
                reason="High cross-encoder relevance score and high keyword overlap in top candidates",
            )

        # 4. Ambiguous zone (0.15 <= score < 0.45, or low keyword overlap) -> Formulate corrective query
        reformulated = self._reformulate_corrective(query, candidates, matched_words, query_words)
        logger.info(f"CRAG Ambiguous: top score {top_score:.4f}, reformulating query -> '{reformulated}'")
        return CRAGAssessment(
            status="AMBIGUOUS",
            top_score=round(top_score, 4),
            reformulated_query=reformulated,
            reason=f"Marginal relevance ({top_score:.4f}) or partial keyword overlap ({keyword_overlap_ratio:.2f}); corrective query generated",
        )

    def _reformulate_corrective(
        self,
        query: str,
        candidates: Sequence[Candidate],
        matched_words: list[str],
        query_words: list[str],
    ) -> str:
        """Formulates an improved, focused query to disambiguate retrieval."""
        missing = [w for w in query_words if w not in matched_words]
        clean_terms = [w for w in query_words if w not in STOP_WORDS]

        if missing:
            # Emphasize missing terms
            return f"{' '.join(clean_terms)} {' '.join(missing)}"

        # Strip punctuation and focus on key nouns
        return " ".join(clean_terms)
