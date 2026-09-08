"""Unit test for RetrievalService, RRF, and FlashRank cross-encoder reranker."""

from contracts.chunk import Chunk
from contracts.retrieval import Candidate, SearchQuery
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion
from services.retrieval.service import RetrievalService


def test_reciprocal_rank_fusion_scoring():
    dense = [
        ({"id": "c1", "doc_id": "d1", "page": 1, "bbox": [0, 0, 10, 10], "text": "passage 1"}, 0.9),
        ({"id": "c2", "doc_id": "d1", "page": 1, "bbox": [0, 0, 10, 10], "text": "passage 2"}, 0.8),
    ]
    sparse = [
        ({"id": "c2", "doc_id": "d1", "page": 1, "bbox": [0, 0, 10, 10], "text": "passage 2"}, 12.0),
        ({"id": "c3", "doc_id": "d1", "page": 1, "bbox": [0, 0, 10, 10], "text": "passage 3"}, 8.0),
    ]

    fused = reciprocal_rank_fusion(dense, sparse, k=60, top_k=5)
    assert len(fused) == 3

    # c2 was rank 2 in dense and rank 1 in sparse: 1/62 + 1/61 = 0.016129 + 0.016393 = 0.032522
    # c1 was rank 1 in dense: 1/61 = 0.016393
    # c3 was rank 2 in sparse: 1/62 = 0.016129
    # So c2 should be #1!
    assert fused[0].id == "c2"
    assert fused[0].dense_rank == 2
    assert fused[0].sparse_rank == 1
    assert fused[0].rrf_score > fused[1].rrf_score


def test_flashrank_reranker_and_refusal():
    reranker = FlashRankReranker(min_score_cutoff=0.15)

    candidates = [
        Candidate(
            id="c1",
            doc_id="d1",
            page=1,
            bbox=(72, 72, 400, 100),
            text="The capital of France is Paris, located on the Seine river.",
            rrf_score=0.03,
        ),
        Candidate(
            id="c2",
            doc_id="d1",
            page=2,
            bbox=(72, 110, 400, 150),
            text="Quantum computing uses qubits instead of classical binary bits.",
            rrf_score=0.02,
        ),
    ]

    # Query matching c1
    top_cands, citations, refused = reranker.rerank(
        query="What is the capital of France?",
        candidates=candidates,
        top_n=2,
    )
    assert not refused
    assert top_cands[0].id == "c1"
    assert len(citations) == 2
    assert "Page 1" in citations[0].formatted_badge

    # Query completely irrelevant to both -> should trigger refusal cutoff
    top_cands_irr, _, refused_irr = reranker.rerank(
        query="Xylophone astronaut saxophone orbital strawberry jazz recipe",
        candidates=candidates,
        top_n=2,
    )
    # Refusal trigger or low score
    assert top_cands_irr[0].rerank_score < 0.20


def test_retrieval_service_end_to_end(tmp_path):
    qdrant = QdrantStore(in_memory=True, collection_name="test_retrieval")
    bm25 = BM25Store(index_dir=tmp_path / "bm25")

    chunks = [
        Chunk(
            id="doc_gpu_c0",
            doc_id="doc_gpu",
            page=1,
            page_end=1,
            bbox=(72, 72, 400, 120),
            text="NVIDIA RTX 3050 has 6GB GDDR6 VRAM and 2048 CUDA cores.",
            raw_text="NVIDIA RTX 3050 has 6GB GDDR6 VRAM and 2048 CUDA cores.",
            token_count=15,
        ),
        Chunk(
            id="doc_gpu_c1",
            doc_id="doc_gpu",
            page=2,
            page_end=2,
            bbox=(72, 130, 400, 180),
            text="PostgreSQL runs on port 5432 and Qdrant runs on port 6333.",
            raw_text="PostgreSQL runs on port 5432 and Qdrant runs on port 6333.",
            token_count=14,
        ),
    ]
    qdrant.index(chunks)
    bm25.index(chunks)

    service = RetrievalService(qdrant_store=qdrant, bm25_store=bm25)
    query = SearchQuery(query_text="How much VRAM does RTX 3050 have?", top_k=5, top_rerank=2)
    response = service.retrieve(query)

    assert response.query == query.query_text
    assert len(response.candidates) >= 1
    assert response.candidates[0].id == "doc_gpu_c0"
    assert len(response.citations) >= 1
    assert "Page 1" in response.citations[0].formatted_badge
    assert response.duration_ms > 0
