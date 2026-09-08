"""Unit tests verifying all shared Pydantic data contracts."""

from contracts.chunk import Chunk, IndexRequest, IndexResponse
from contracts.document import Block, BlockType, DocumentProfile, IngestResponse
from contracts.retrieval import Candidate, Citation, RetrieveResponse, SearchQuery


def test_document_contracts():
    block = Block(
        id="doc1_p1_b0",
        doc_id="doc1",
        page=1,
        bbox=(72.0, 72.0, 540.0, 120.0),
        type=BlockType.HEADING,
        text="Executive Summary",
        level=1,
        order=0,
    )
    assert block.type == BlockType.HEADING
    assert block.level == 1

    profile = DocumentProfile(
        route="fast_text",
        page_count=10,
        sample_pages=[1, 2, 5, 9, 10],
        text_coverage=0.85,
        chars_per_page=2200.0,
        image_ratio=0.05,
        columns=1,
        table_score=0.1,
        reason="clean digital PDF with standard single column text",
    )
    assert profile.route == "fast_text"

    response = IngestResponse(
        doc_id="doc1",
        file_path="data/test.pdf",
        profile=profile,
        blocks=[block],
        duration_ms=45.2,
    )
    assert response.doc_id == "doc1"
    assert len(response.blocks) == 1


def test_chunk_contracts():
    chunk = Chunk(
        id="doc1_c0",
        doc_id="doc1",
        page=1,
        page_end=1,
        bbox=(72.0, 72.0, 540.0, 120.0),
        text="# Executive Summary\n\nQ3 revenue reached 10M.",
        raw_text="Q3 revenue reached 10M.",
        token_count=15,
        headings=["Executive Summary"],
        is_table=False,
    )
    assert chunk.token_count <= 512

    index_req = IndexRequest(doc_id="doc1", chunks=[chunk])
    assert index_req.doc_id == "doc1"
    index_res = IndexResponse(
        doc_id="doc1",
        indexed_count=1,
        dense_indexed=True,
        sparse_indexed=True,
        duration_ms=12.5,
    )
    assert index_res.indexed_count == 1


def test_retrieval_contracts():
    query = SearchQuery(query_text="What was the revenue?")
    assert query.top_k == 20
    assert query.min_rerank_score == 0.15

    candidate = Candidate(
        id="doc1_c0",
        doc_id="doc1",
        page=1,
        bbox=(72.0, 72.0, 540.0, 120.0),
        text="Q3 revenue reached 10M.",
        dense_rank=1,
        sparse_rank=2,
        rrf_score=0.032,
        rerank_score=0.88,
    )

    citation = Citation(
        doc_id="doc1",
        page=1,
        bbox=(72.0, 72.0, 540.0, 120.0),
        snippet="Q3 revenue reached 10M.",
        formatted_badge="[doc1: Page 1, (72.0, 72.0, 540.0, 120.0)]",
    )

    retrieve_res = RetrieveResponse(
        query=query.query_text,
        candidates=[candidate],
        citations=[citation],
        refused=False,
        top_score=0.88,
        duration_ms=25.0,
    )
    assert not retrieve_res.refused
    assert retrieve_res.top_score >= 0.15


def test_graph_contracts():
    from contracts.graph import (
        Entity,
        GraphCommunity,
        GraphNeighborhood,
        GraphRAGResponse,
        Relation,
    )

    entity = Entity(
        name="RTX 3050",
        category="HARDWARE",
        doc_id="doc1",
        chunk_id="c1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
    )
    assert entity.name == "RTX 3050"
    assert entity.category == "HARDWARE"

    relation = Relation(
        source="RTX 3050",
        predicate="has_memory",
        target="6GB VRAM",
        doc_id="doc1",
        chunk_id="c1",
    )
    assert relation.predicate == "has_memory"

    nb = GraphNeighborhood(
        center_entities=["RTX 3050"],
        entities=[entity],
        relations=[relation],
        connected_chunk_ids=["c1"],
    )
    assert len(nb.entities) == 1

    comm = GraphCommunity(
        community_id=0,
        name="Hardware Cluster",
        entities=["RTX 3050", "6GB VRAM"],
    )
    assert len(comm.entities) == 2

    rag_res = GraphRAGResponse(
        query="What is the RTX 3050?",
        matched_entities=[entity],
        relations=[relation],
        subgraph_text="- RTX 3050 has_memory 6GB VRAM",
        connected_chunk_ids=["c1"],
        communities=[comm],
        duration_ms=5.5,
    )
    assert rag_res.duration_ms == 5.5
    assert len(rag_res.relations) == 1


def test_compactor_contracts():
    from contracts.compactor import CompactedContext, CompactorRequest, CompressedChunk

    chunk = CompressedChunk(
        id="c1",
        doc_id="doc1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        original_text="Long uncompressed text with extra sentences.",
        compressed_text="Salient sentence.",
        original_tokens=30,
        compressed_tokens=10,
        compression_ratio=0.33,
    )
    assert chunk.compression_ratio == 0.33

    context = CompactedContext(
        query="test query",
        chunks=[chunk],
        total_original_tokens=30,
        total_compressed_tokens=10,
        overall_compression_ratio=0.33,
        budget_tokens=3072,
        dropped_chunks_count=0,
        deduplicated_sentences_count=2,
        pruned_table_columns_count=1,
        formatted_prompt_context="Source: Salient sentence.",
        duration_ms=1.2,
    )
    assert context.budget_tokens == 3072
    assert context.deduplicated_sentences_count == 2

    req = CompactorRequest(
        query="test query",
        candidates=[],
        budget_tokens=2048,
    )
    assert req.budget_tokens == 2048

