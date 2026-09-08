"""Unit test for IndexingService, QdrantStore, and BM25Store."""

from pathlib import Path

from contracts.chunk import Chunk
from contracts.document import Block, BlockType
from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.indexing.service import IndexingService


def test_qdrant_store_in_memory():
    store = QdrantStore(in_memory=True, collection_name="test_collection")
    chunk = Chunk(
        id="d1_c0",
        doc_id="d1",
        page=1,
        page_end=1,
        bbox=(72, 72, 400, 100),
        text="Dense vector search test passage.",
        raw_text="Dense vector search test passage.",
        token_count=10,
    )
    count = store.index([chunk])
    assert count == 1

    results = store.search("vector search", top_k=5)
    assert len(results) >= 1
    assert results[0][0]["id"] == "d1_c0"
    assert -1.0 <= results[0][1] <= 1.0


def test_bm25_store_disk(tmp_path: Path):
    store = BM25Store(index_dir=tmp_path / "bm25")
    chunk1 = Chunk(
        id="d1_c0",
        doc_id="d1",
        page=1,
        page_end=1,
        bbox=(72, 72, 400, 100),
        text="The quarterly financial revenue exceeded expectations.",
        raw_text="The quarterly financial revenue exceeded expectations.",
        token_count=10,
    )
    chunk2 = Chunk(
        id="d1_c1",
        doc_id="d1",
        page=2,
        page_end=2,
        bbox=(72, 110, 400, 150),
        text="Engineering milestones achieved on time.",
        raw_text="Engineering milestones achieved on time.",
        token_count=8,
    )

    store.index([chunk1, chunk2])

    results = store.search("quarterly financial", top_k=2)
    assert len(results) >= 1
    assert results[0][0]["id"] == "d1_c0"


def test_indexing_service_end_to_end(tmp_path: Path):
    service = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")

    blocks = [
        Block(
            id="d1_p1_b0",
            doc_id="d1",
            page=1,
            bbox=(72, 72, 500, 100),
            type=BlockType.HEADING,
            text="Cloud Operations",
            level=1,
            order=0,
        ),
        Block(
            id="d1_p1_b1",
            doc_id="d1",
            page=1,
            bbox=(72, 110, 500, 200),
            type=BlockType.TEXT,
            text="Kubernetes clusters deployed across multi-region availability zones.",
            order=1,
        ),
    ]

    res = service.chunk_and_index(doc_id="d1", blocks=blocks)
    assert res.doc_id == "d1"
    assert res.indexed_count >= 1
    assert res.dense_indexed
    assert res.sparse_indexed
    assert res.duration_ms > 0
