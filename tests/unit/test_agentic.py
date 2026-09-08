"""Unit tests for Phase 12: Agentic RAG, Query Decomposition, and CRAG Reflection."""

from unittest.mock import MagicMock

from contracts.retrieval import Candidate, Citation, RetrieveResponse
from services.retrieval.agentic import AgenticCoordinator
from services.retrieval.crag import CRAGEvaluator
from services.retrieval.decomposer import QueryDecomposer


def test_decomposer_multi_hop_detection():
    decomposer = QueryDecomposer(ollama_url="http://mock:11434")
    assert decomposer.is_multi_hop_candidate("Compare Abhishek's work at Syngene with his work at prior companies")
    assert decomposer.is_multi_hop_candidate("What is the dense latency vs sparse latency in benchmark?")
    assert decomposer.is_multi_hop_candidate("Explain the architecture diagram, and what is the VRAM usage?")
    assert not decomposer.is_multi_hop_candidate("What is the dense retrieval latency of RTX 3050?")


def test_decomposer_heuristic_splitting():
    decomposer = QueryDecomposer(ollama_url="http://mock:11434")

    # 1. Compare X and Y
    plan1 = decomposer._decompose_heuristic("Compare Syngene project with Bristol Myers Squibb")
    assert plan1.is_multi_hop is True
    assert len(plan1.sub_queries) == 2
    assert "Syngene" in plan1.sub_queries[0].query_text
    assert "Bristol" in plan1.sub_queries[1].query_text

    # 2. X vs Y
    plan2 = decomposer._decompose_heuristic("Qdrant HNSW vs BM25s lexical search")
    assert plan2.is_multi_hop is True
    assert len(plan2.sub_queries) == 2
    assert "Qdrant HNSW" in plan2.sub_queries[0].query_text
    assert "BM25s" in plan2.sub_queries[1].query_text


def test_crag_evaluator_confident():
    evaluator = CRAGEvaluator(confident_threshold=0.45, refusal_threshold=0.15)
    candidates = [
        Candidate(
            id="c1",
            doc_id="doc1",
            page=1,
            bbox=(0.0, 0.0, 100.0, 100.0),
            text="The NVIDIA GeForce RTX 3050 Laptop GPU achieves 18.5 ms dense latency with 2.2 GB VRAM.",
            rerank_score=0.88,
        )
    ]
    assessment = evaluator.evaluate("What is the RTX 3050 dense latency and VRAM?", candidates)
    assert assessment.status == "CONFIDENT"
    assert assessment.top_score == 0.88
    assert assessment.reformulated_query is None


def test_crag_evaluator_ambiguous_reformulation():
    evaluator = CRAGEvaluator(confident_threshold=0.45, refusal_threshold=0.15)
    candidates = [
        Candidate(
            id="c2",
            doc_id="doc2",
            page=2,
            bbox=(0.0, 0.0, 100.0, 100.0),
            text="The hardware system supports low-power modes and standard inference.",
            rerank_score=0.32,  # in ambiguous zone [0.15, 0.45)
        )
    ]
    assessment = evaluator.evaluate("What is the quantum cryptographic key distribution protocol?", candidates)
    assert assessment.status == "AMBIGUOUS"
    assert assessment.top_score == 0.32
    assert assessment.reformulated_query is not None
    assert "quantum" in assessment.reformulated_query.lower()


def test_crag_evaluator_refusal():
    evaluator = CRAGEvaluator(confident_threshold=0.45, refusal_threshold=0.15)
    candidates = [
        Candidate(
            id="c3",
            doc_id="doc3",
            page=1,
            bbox=(0.0, 0.0, 100.0, 100.0),
            text="Unrelated text about weather in Honolulu.",
            rerank_score=0.08,  # Below 0.15
        )
    ]
    assessment = evaluator.evaluate("How does the RRF k=60 parameter operate?", candidates)
    assert assessment.status == "REFUSE"
    assert assessment.top_score == 0.08
    assert assessment.reformulated_query is None


def test_agentic_coordinator_multi_hop_run():
    mock_retrieval = MagicMock()
    mock_reranker = MagicMock()

    # Sub-query 1 returns doc1
    c1 = Candidate(
        id="c1",
        doc_id="doc1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        text="Abhishek built LLM pipelines at Syngene.",
        rerank_score=0.75,
    )
    cit1 = Citation(
        doc_id="doc1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        snippet="Abhishek at Syngene",
        formatted_badge="[doc1: 1]",
    )
    res1 = RetrieveResponse(
        query="q1",
        candidates=[c1],
        citations=[cit1],
        top_score=0.75,
        duration_ms=12.5,
        refused=False,
    )

    # Sub-query 2 returns doc2
    c2 = Candidate(
        id="c2",
        doc_id="doc2",
        page=3,
        bbox=(0.0, 0.0, 100.0, 100.0),
        text="RTX 3050 uses 2.2 GB VRAM in benchmark.",
        rerank_score=0.82,
    )
    cit2 = Citation(
        doc_id="doc2",
        page=3,
        bbox=(0.0, 0.0, 100.0, 100.0),
        snippet="RTX 3050 2.2 GB",
        formatted_badge="[doc2: 3]",
    )
    res2 = RetrieveResponse(
        query="q2",
        candidates=[c2],
        citations=[cit2],
        top_score=0.82,
        duration_ms=14.0,
        refused=False,
    )

    mock_retrieval.retrieve.side_effect = [res1, res2]
    mock_reranker.rerank.return_value = (
        [c2, c1],
        [cit2, cit1],
        False,
    )

    coordinator = AgenticCoordinator(
        retrieval_service=mock_retrieval,
        reranker=mock_reranker,
    )

    query = "Compare Abhishek's work at Syngene and the RTX 3050 hardware benchmark"
    cands, cits, steps, plan, crag_res, refused = coordinator.run_plan(query, force_multi_hop=True)

    assert not refused
    assert len(cands) == 2
    assert len(cits) == 2
    assert len(steps) >= 3
    assert plan.is_multi_hop is True
    assert crag_res.status == "CONFIDENT"

    # Test prompt generation
    prompt = coordinator.build_agentic_prompt(query, cands, plan)
    assert "Comparative Synthesis" in prompt
    assert "Abhishek" in prompt or "Syngene" in prompt
