"""Unit tests verifying resolution of the false 0.15 relevance cutoff refusal on exploratory and scoped queries."""

from unittest.mock import MagicMock

from contracts.retrieval import Candidate, SearchQuery
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.crag import CRAGEvaluator
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion
from services.retrieval.service import RetrievalService


def test_exploratory_intent_detection():
    """Validates that broad, summary, and overview queries are recognized as exploratory."""
    assert FlashRankReranker.is_exploratory_or_summary_query("tell me about the document")
    assert FlashRankReranker.is_exploratory_or_summary_query("tell me about the document?")
    assert FlashRankReranker.is_exploratory_or_summary_query("what is this document about?")
    assert FlashRankReranker.is_exploratory_or_summary_query("summarize this report")
    assert FlashRankReranker.is_exploratory_or_summary_query("give me an overview of this file")
    assert FlashRankReranker.is_exploratory_or_summary_query("explain this document")
    assert FlashRankReranker.is_exploratory_or_summary_query("what does this file say?")
    # Factoid queries should NOT be classified as exploratory
    assert not FlashRankReranker.is_exploratory_or_summary_query("what is the total net income in Q4 2024?")
    assert not FlashRankReranker.is_exploratory_or_summary_query("show the transaction on 29/08/2024")


def test_rrf_normalization_scale():
    """Verifies that RRF scores are normalized relative to theoretical max rank 1 score."""
    dense = [({"id": "c1", "doc_id": "doc1", "text": "hello"}, 0.95)]
    sparse = [({"id": "c1", "doc_id": "doc1", "text": "hello"}, 2.5)]

    candidates = reciprocal_rank_fusion(dense, sparse, k=60, top_k=5)
    assert len(candidates) == 1
    # Rank 1 in both should yield 1.0 (or very close to 1.0)
    assert candidates[0].rrf_score == 1.0


def test_crag_evaluator_exploratory_non_refusal():
    """Verifies that CRAGEvaluator does not falsely trigger REFUSE on exploratory queries."""
    crag = CRAGEvaluator(confident_threshold=0.45, refusal_threshold=0.15)
    candidates = [
        Candidate(
            id="c1",
            doc_id="epf_passbook.pdf",
            page=1,
            bbox=(0, 0, 100, 100),
            text="Member Passbook showing employee and employer PF contributions",
            rrf_score=0.85,
            rerank_score=0.64,
        )
    ]
    assessment = crag.evaluate("tell me about the document", candidates)
    assert assessment.status == "CONFIDENT"
    assert assessment.top_score >= 0.15


def test_retrieval_service_scoped_exploratory_query():
    """Verifies that RetrievalService retrieves target document and does not refuse on exploratory query."""
    mock_qdrant = MagicMock(spec=QdrantStore)
    mock_bm25 = MagicMock(spec=BM25Store)

    # Scoped target doc
    target_doc = "bgbng20125150000010074_2021_0cb35b3e"

    # BM25 helper resolution
    mock_bm25.resolve_matching_doc_ids.return_value = [target_doc]
    mock_bm25.get_document_overview_chunks.return_value = [
        {
            "id": "c_page1",
            "doc_id": target_doc,
            "page": 1,
            "bbox": [0.0, 0.0, 100.0, 100.0],
            "text": "EPF Member Passbook for financial year 2021-2022",
            "headings": ["Passbook Overview"],
            "is_table": False,
        }
    ]

    # Qdrant returns chunk for target doc
    mock_qdrant.search.return_value = [
        (
            {
                "id": "c_page1",
                "doc_id": target_doc,
                "page": 1,
                "bbox": [0.0, 0.0, 100.0, 100.0],
                "text": "EPF Member Passbook for financial year 2021-2022",
            },
            0.82,
        )
    ]
    mock_bm25.search.return_value = []

    service = RetrievalService(qdrant_store=mock_qdrant, bm25_store=mock_bm25)
    resp = service.retrieve(
        SearchQuery(
            query_text="tell me about the document?",
            top_k=5,
            top_rerank=6,
            min_rerank_score=0.15,
            doc_ids=[target_doc],
        )
    )

    # Verify pre-filtering was passed
    mock_qdrant.search.assert_called_once()
    assert mock_qdrant.search.call_args.kwargs["doc_ids"] == [target_doc]

    # Verify non-refusal and grounded response
    assert not resp.refused
    assert resp.top_score >= 0.15
    assert len(resp.candidates) >= 1
    assert resp.candidates[0].doc_id == target_doc
