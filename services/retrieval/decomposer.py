"""Query Decomposition for Phase 12: Agentic Multi-Hop Reasoning."""

import json
import re
from typing import Any

import requests

from contracts.agent import DecompositionPlan, SubQuery
from services.common.logger import get_logger

logger = get_logger("query_decomposer")

# Regex patterns identifying multi-hop queries
COMPARISON_PATTERNS = [
    r"\bcompare\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"\bdifference between\b",
    r"\band also\b",
    r"\bas well as\b",
    r"\bboth\b.*\band\b",
    r"\bhow does\b.*\bcompare to\b",
]


class QueryDecomposer:
    """Decomposes complex multi-faceted queries into atomic, targeted sub-queries."""

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "llama3.2:3b") -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def is_multi_hop_candidate(self, query: str) -> bool:
        """Determines if a query requires multi-hop retrieval based on keywords and syntax."""
        lower = query.lower()
        for pat in COMPARISON_PATTERNS:
            if re.search(pat, lower):
                return True
        # Check for multiple question marks or semicolon delimiters
        if query.count("?") > 1 or ";" in query:
            return True
        # Check for conjunctive compound sentences (e.g. "..., and what ...")
        if re.search(r",\s*(and|while|whereas)\s+", lower):
            return True
        return False

    def decompose(self, query: str, force_multi_hop: bool = False) -> DecompositionPlan:
        """Decomposes a query into atomic sub-queries.

        Falls back to rule-based heuristic decomposition if LLM is unavailable or unneeded.
        """
        is_multi = force_multi_hop or self.is_multi_hop_candidate(query)
        if not is_multi:
            return DecompositionPlan(
                original_query=query,
                is_multi_hop=False,
                sub_queries=[
                    SubQuery(
                        query_text=query.strip(),
                        rationale="Single-hop atomic retrieval",
                        hop_index=0,
                    )
                ],
            )

        # Attempt fast LLM decomposition if server reachable
        plan = self._decompose_with_llm(query)
        if plan and len(plan.sub_queries) > 1:
            return plan

        # Heuristic rule-based decomposition fallback
        return self._decompose_heuristic(query)

    def _decompose_heuristic(self, query: str) -> DecompositionPlan:
        """Splits multi-aspect questions using linguistic conjunctions and markers."""
        logger.info(f"Applying heuristic decomposition on: {query}")
        clean = query.strip().rstrip("?")
        sub_texts: list[str] = []

        # Check for "compare X and/with/to Y"
        cmp_match = re.match(r"^compare\s+(.+?)\s+(?:with|to|and)\s+(.+)$", clean, re.IGNORECASE)
        if cmp_match:
            sub_texts = [cmp_match.group(1).strip(), cmp_match.group(2).strip()]
        elif " vs " in clean.lower() or " versus " in clean.lower():
            parts = re.split(r"\s+vs\.?\s+|\s+versus\s+", clean, flags=re.IGNORECASE)
            sub_texts = [p.strip() for p in parts if p.strip()]
        elif ", and " in clean.lower():
            parts = clean.split(", and ")
            sub_texts = [p.strip() for p in parts if p.strip()]
        elif " and also " in clean.lower():
            parts = clean.split(" and also ")
            sub_texts = [p.strip() for p in parts if p.strip()]
        elif " as well as " in clean.lower():
            parts = clean.split(" as well as ")
            sub_texts = [p.strip() for p in parts if p.strip()]
        elif " and " in clean.lower() and len(clean.split(" and ")) == 2:
            parts = clean.split(" and ")
            sub_texts = [p.strip() for p in parts if p.strip()]
        else:
            sub_texts = [clean]

        sub_queries = [
            SubQuery(
                query_text=txt if txt.endswith("?") else f"{txt}?",
                rationale=f"Aspect {i + 1} retrieval target",
                hop_index=i,
            )
            for i, txt in enumerate(sub_texts[:3])
        ]

        return DecompositionPlan(
            original_query=query,
            is_multi_hop=len(sub_queries) > 1,
            sub_queries=sub_queries,
        )

    def _decompose_with_llm(self, query: str) -> DecompositionPlan | None:
        """Prompts local Ollama to break down the query into JSON sub-queries."""
        prompt = (
            f"You are a retrieval planner. Break this complex question into 2 or 3 distinct sub-questions "
            f"for searching a knowledge base:\n"
            f"Question: {query}\n\n"
            f"Respond ONLY with a JSON array of strings, e.g.: [\"sub-question 1\", \"sub-question 2\"]"
        )
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "num_predict": 128},
                },
                timeout=4.0,
            )
            if resp.status_code == 200:
                body = resp.json()
                raw = body.get("response", "").strip()
                data: Any = json.loads(raw)
                if isinstance(data, dict):
                    # might be wrapped in {"questions": [...]} or {"sub_queries": [...]}
                    for v in data.values():
                        if isinstance(v, list):
                            data = v
                            break
                if isinstance(data, list) and len(data) >= 2:
                    sub_queries = [
                        SubQuery(query_text=str(q).strip(), rationale="LLM decomposed sub-goal", hop_index=i)
                        for i, q in enumerate(data[:3])
                    ]
                    logger.info(f"LLM decomposed into {len(sub_queries)} hops")
                    return DecompositionPlan(
                        original_query=query,
                        is_multi_hop=True,
                        sub_queries=sub_queries,
                    )
        except Exception as exc:
            logger.debug(f"LLM decomposition skipped ({exc}), using heuristic")

        return None
