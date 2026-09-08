"""Full end-to-end integration test across all SOA services."""

from pathlib import Path

import fitz
import pytest

from contracts.document import IngestRequest
from contracts.retrieval import SearchQuery
from services.common.logger import LOGS_DIR
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.retrieval.service import RetrievalService


@pytest.fixture
def complex_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "system_architecture_spec.pdf"
    doc = fitz.open()

    # Page 1: Heading + Technical Details
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((72, 72), "Enterprise System Architecture", fontsize=18)
    page1.insert_text(
        (72, 110),
        "The distributed platform relies on an NVIDIA GeForce RTX 3050 Laptop GPU with 6GB VRAM. "
        "PostgreSQL operates as the primary relational database on port 5432, while Qdrant serves vector queries on port 6333.",
        fontsize=11,
    )

    # Page 2: Table + Benchmarks
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 72), "Performance Benchmarks", fontsize=16)
    page2.insert_text(
        (72, 110),
        "Reciprocal Rank Fusion fuses dense and sparse result sets using constant k=60 to eliminate ranking bias. "
        "FlashRank cross-encoder reranks top-20 candidates down to top-6 with a minimum refusal threshold of 0.15.",
        fontsize=11,
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_full_rag_pipeline_end_to_end(complex_pdf: Path, tmp_path: Path):
    # 1. Initialize SOA Services
    ingestion = IngestionService()
    indexing = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    retrieval = RetrievalService(qdrant_store=indexing.qdrant, bm25_store=indexing.bm25)

    # 2. Ingestion Service: 8-page probe -> Block extraction
    ingest_req = IngestRequest(file_path=str(complex_pdf))
    ingest_res = ingestion.parse(ingest_req)

    assert ingest_res.profile.route in ("fast_text", "layout")
    assert len(ingest_res.blocks) >= 2
    assert ingest_res.doc_id.startswith("system_architecture_spec_")

    # 3. Indexing Service: Hierarchy chunking -> Qdrant HNSW + BM25s
    index_res = indexing.chunk_and_index(doc_id=ingest_res.doc_id, blocks=ingest_res.blocks)

    assert index_res.indexed_count >= 2
    assert index_res.dense_indexed
    assert index_res.sparse_indexed

    # 4. Retrieval Service: Dual query -> RRF k=60 -> FlashRank rerank -> Citations
    query = SearchQuery(
        query_text="What GPU and VRAM are used in the platform?",
        top_k=10,
        top_rerank=3,
        min_rerank_score=0.15,
    )
    retrieve_res = retrieval.retrieve(query)

    assert not retrieve_res.refused
    assert len(retrieve_res.candidates) >= 1
    assert "RTX 3050" in retrieve_res.candidates[0].text
    assert "6GB VRAM" in retrieve_res.candidates[0].text

    # Verify Provenance Citations
    assert len(retrieve_res.citations) >= 1
    cite = retrieve_res.citations[0]
    assert cite.page == 1
    assert "Page 1" in cite.formatted_badge
    assert len(cite.bbox) == 4

    # Verify Central Logging
    log_file = LOGS_DIR / "rag_system.log"
    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "rag.ingestion" in log_content
    assert "rag.indexing" in log_content
    assert "rag.retrieval" in log_content
