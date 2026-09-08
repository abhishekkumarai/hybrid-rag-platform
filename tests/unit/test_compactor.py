"""Unit tests for Phase 14: Contextual Compression & Adaptive Token Budget Compactor."""

from contracts.retrieval import Candidate
from services.retrieval.compactor import (
    ContextCompactor,
    calculate_jaccard_similarity,
    estimate_tokens,
    score_sentence_salience,
)


def test_token_estimation_and_jaccard():
    text = "The NVIDIA RTX 3050 Laptop GPU achieves fast local inference with 6GB VRAM."
    tokens = estimate_tokens(text)
    assert 10 <= tokens <= 20

    s1 = "NVIDIA RTX 3050 has 6GB of high speed VRAM memory."
    s2 = "The RTX 3050 has 6GB of fast VRAM memory."
    s3 = "Weather in Tokyo is cloudy with light rain."

    sim_high = calculate_jaccard_similarity(s1, s2)
    sim_low = calculate_jaccard_similarity(s1, s3)

    assert sim_high >= 0.50
    assert sim_low == 0.0


def test_sentence_salience_scoring():
    query = "What is the dense latency and VRAM usage on RTX 3050?"
    salient_sent = "The RTX 3050 achieves 18.5 ms dense latency with 2.2 GB VRAM allocated."
    filler_sent = "This chapter discusses introductory background concepts and generic computing principles."

    score_salient = score_sentence_salience(salient_sent, query, candidate_score=0.8)
    score_filler = score_sentence_salience(filler_sent, query, candidate_score=0.8)

    assert score_salient > score_filler
    assert score_salient >= 0.50


def test_table_column_pruning():
    compactor = ContextCompactor()
    table_markdown = (
        "| Hardware Model | Architecture | VRAM | TDP | Price | Dense Latency |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| RTX 3050 | Ampere | 6GB | 60W | $799 | 18.5ms |\n"
        "| RTX 4090 | Ada | 24GB | 450W | $1599 | 4.2ms |\n"
    )
    query = "What is the VRAM and Dense Latency of RTX 3050?"

    pruned_text, pruned_cols = compactor.prune_markdown_table(table_markdown, query)

    assert pruned_cols >= 2
    assert "Hardware Model" in pruned_text  # Col 0 preserved
    assert "VRAM" in pruned_text
    assert "Dense Latency" in pruned_text
    assert "Price" not in pruned_text or "TDP" not in pruned_text


def test_cross_passage_redundancy_deduplication():
    compactor = ContextCompactor(default_budget_tokens=3072, redundancy_similarity_threshold=0.70)

    # Two overlapping chunks from adjacent sliding windows or repeated boilerplate
    c1 = Candidate(
        id="c1",
        doc_id="doc1",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        text=(
            "The platform enforces strict Ollama 8K context envelope limits. "
            "FlashRank executes cross-encoder reranking exclusively on the host CPU."
        ),
        rerank_score=0.90,
    )
    c2 = Candidate(
        id="c2",
        doc_id="doc2",
        page=2,
        bbox=(0.0, 50.0, 100.0, 150.0),
        text=(
            "The platform enforces strict Ollama 8K context envelope limits. "
            "Qdrant provides HNSW vector search on port 6333."
        ),
        rerank_score=0.85,
    )

    result = compactor.compress_candidates(
        query="What context limits and CPU components are used?",
        candidates=[c1, c2],
        deduplicate=True,
    )

    assert result.deduplicated_sentences_count >= 1
    # Check that the duplicate sentence was only retained once in the formatted context
    dup_phrase = "strict Ollama 8K context envelope limits"
    count = result.formatted_prompt_context.count(dup_phrase)
    assert count == 1


def test_strict_token_budget_packing():
    # Budget set very small (e.g. 35 tokens) to force partial packing or dropping
    compactor = ContextCompactor(default_budget_tokens=35)

    c1 = Candidate(
        id="c1",
        doc_id="doc1",
        page=1,
        bbox=(10.0, 10.0, 200.0, 50.0),
        text="The primary database is Qdrant running HNSW cosine search. It indexes embeddings rapidly.",
        rerank_score=0.95,
    )
    c2 = Candidate(
        id="c2",
        doc_id="doc1",
        page=2,
        bbox=(10.0, 60.0, 200.0, 100.0),
        text="Another long passage with detailed information about Redis queuing and recovery workers.",
        rerank_score=0.70,
    )
    c3 = Candidate(
        id="c3",
        doc_id="doc2",
        page=5,
        bbox=(20.0, 20.0, 300.0, 80.0),
        text="A third candidate that should be dropped because the budget is exhausted.",
        rerank_score=0.60,
    )

    result = compactor.compress_candidates(
        query="Tell me about Qdrant and Redis database",
        candidates=[c1, c2, c3],
        budget_tokens=35,
    )

    assert result.total_compressed_tokens <= 35
    assert result.dropped_chunks_count >= 1
    assert len(result.chunks) >= 1

    # Verify preserved coordinates on retained chunks
    first_chunk = result.chunks[0]
    assert first_chunk.id == "c1"
    assert first_chunk.doc_id == "doc1"
    assert first_chunk.page == 1
    assert first_chunk.bbox == (10.0, 10.0, 200.0, 50.0)
    assert first_chunk.compression_ratio <= 1.0
