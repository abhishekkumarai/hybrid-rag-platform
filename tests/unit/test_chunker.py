"""Unit tests for content-aware chunker with sliding window overlap and token caps (REC-59)."""

from contracts.document import Block, BlockType
from services.indexing.chunker import (
    chunk_blocks,
    estimate_tokens,
    extract_overlap_prefix,
    split_large_table,
    split_text_recursive,
)


def test_chunking_heading_breadcrumbs():
    blocks = [
        Block(
            id="d1_p1_b0",
            doc_id="d1",
            page=1,
            bbox=(72, 72, 500, 100),
            type=BlockType.HEADING,
            text="Financial Performance",
            level=1,
            order=0,
        ),
        Block(
            id="d1_p1_b1",
            doc_id="d1",
            page=1,
            bbox=(72, 105, 500, 130),
            type=BlockType.HEADING,
            text="Revenue Growth",
            level=2,
            order=1,
        ),
        Block(
            id="d1_p1_b2",
            doc_id="d1",
            page=1,
            bbox=(72, 140, 500, 200),
            type=BlockType.TEXT,
            text="Revenue grew by 20% in the third quarter.",
            order=2,
        ),
    ]

    chunks = chunk_blocks(blocks, doc_id="d1", max_tokens=512)
    assert len(chunks) >= 1
    # Check that breadcrumbs are present in the text
    assert "Financial Performance > Revenue Growth" in chunks[-1].text
    assert chunks[-1].headings == ["Financial Performance", "Revenue Growth"]
    assert chunks[-1].token_count <= 512


def test_chunking_table_windowing():
    table_text = (
        "| Quarter | Revenue | Profit |\n"
        "| --- | --- | --- |\n"
        "| Q1 | $10M | $2M |\n"
        "| Q2 | $12M | $3M |\n"
        "| Q3 | $15M | $4M |\n"
    )
    blocks = [
        Block(
            id="d1_p1_b0",
            doc_id="d1",
            page=1,
            bbox=(72, 72, 500, 300),
            type=BlockType.TABLE,
            text=table_text,
            order=0,
        )
    ]

    chunks = chunk_blocks(blocks, doc_id="d1", max_tokens=512)
    assert len(chunks) == 1
    assert chunks[0].is_table
    assert "| Quarter | Revenue | Profit |" in chunks[0].text
    assert chunks[0].token_count <= 512


def test_oversized_table_split():
    # Construct a large table
    header = "| Metric | Value |\n| --- | --- |\n"
    rows = "\n".join([f"| Metric {i} | Value {i} with extended description details |" for i in range(100)])
    full_table = header + rows

    splits = split_large_table(full_table, max_tokens=200)
    assert len(splits) > 1
    # Every split must have the header row
    for s in splits:
        assert "| Metric | Value |" in s
        assert "| --- | --- |" in s


def test_table_row_overlap_and_breadcrumb_budgeting():
    header = "| Parameter | Specification |\n| --- | --- |\n"
    rows = "\n".join([f"| Param {i:02d} | Setting {i:02d} configured for production |" for i in range(30)])
    full_table = header + rows

    blocks = [
        Block(
            id="d1_h1",
            doc_id="d1",
            page=1,
            bbox=(72, 50, 500, 80),
            type=BlockType.HEADING,
            text="System Architecture Specification Guidelines",
            level=1,
            order=0,
        ),
        Block(
            id="d1_t1",
            doc_id="d1",
            page=1,
            bbox=(72, 90, 500, 600),
            type=BlockType.TABLE,
            text=full_table,
            order=1,
        ),
    ]

    chunks = chunk_blocks(blocks, doc_id="d1", max_tokens=150)
    assert len(chunks) > 1
    for c in chunks:
        assert c.is_table is True
        assert c.token_count <= 150
        assert "Table (System Architecture Specification Guidelines):" in c.text
        assert "| Parameter | Specification |" in c.text

    # Verify row overlap across consecutive chunks (excluding header row)
    chunk_0_lines = [line.strip() for line in chunks[0].text.split("\n") if line.startswith("| Param ")]
    chunk_1_lines = [line.strip() for line in chunks[1].text.split("\n") if line.startswith("| Param ")]
    assert len(chunk_0_lines) > 0
    assert len(chunk_1_lines) > 0
    # The last row of chunk 0 should appear as the first row of chunk 1
    assert chunk_0_lines[-1] == chunk_1_lines[0]


def test_split_text_sliding_window_overlap():
    text = (
        "Artificial intelligence is transforming document search and knowledge retrieval. "
        "Dense vectors capture deep semantic relationships between diverse user queries and paragraphs. "
        "Sparse BM25 algorithms ensure high precision on exact keywords, identifiers, and codes. "
        "Hybrid retrieval integrates both paradigms using Reciprocal Rank Fusion to deliver superior recall. "
        "Cross-encoder rerankers then score candidates with joint attention for optimal relevance. "
        "Finally, large language models synthesize coherent responses strictly grounded in verified citations."
    )

    splits = split_text_recursive(text, max_tokens=45, overlap=15)
    assert len(splits) >= 2
    for s in splits:
        assert estimate_tokens(s) <= 45

    # Check that consecutive splits exhibit non-empty textual overlap
    for i in range(len(splits) - 1):
        words_tail = set(splits[i].split()[-6:])
        words_head = set(splits[i + 1].split()[:6])
        overlap = words_tail.intersection(words_head)
        assert len(overlap) > 0, f"Expected overlap between split {i} and {i+1}, but found none."


def test_sub_sentence_fallback_hard_cap():
    # Construct an oversized single sentence without punctuation (600 words)
    giant_sentence = "This is an unpunctuated massive run-on sentence " + " ".join(
        [f"term_{i}" for i in range(600)]
    )

    splits = split_text_recursive(giant_sentence, max_tokens=100, overlap=20)
    assert len(splits) > 1
    for s in splits:
        assert estimate_tokens(s) <= 100


def test_orphan_headings_preservation():
    blocks = [
        Block(
            id="d1_h1",
            doc_id="d1",
            page=1,
            bbox=(72, 72, 500, 100),
            type=BlockType.HEADING,
            text="Document Title Only",
            level=1,
            order=0,
        )
    ]
    chunks = chunk_blocks(blocks, doc_id="d1", max_tokens=512)
    assert len(chunks) == 1
    assert "Document Title Only" in chunks[0].text
    assert chunks[0].headings == ["Document Title Only"]
    assert chunks[0].token_count <= 512


def test_bounding_box_resolution_per_split():
    blocks = [
        Block(
            id="d1_b0",
            doc_id="d1",
            page=1,
            bbox=(50.0, 50.0, 400.0, 150.0),
            type=BlockType.TEXT,
            text="First section discusses initial quarterly financial projections and revenue metrics.",
            order=0,
        ),
        Block(
            id="d1_b1",
            doc_id="d1",
            page=1,
            bbox=(50.0, 200.0, 400.0, 300.0),
            type=BlockType.TEXT,
            text="Second section focuses entirely on risk assessment, supply chain vulnerabilities, and mitigation plans.",
            order=1,
        ),
    ]

    chunks = chunk_blocks(blocks, doc_id="d1", max_tokens=30, overlap_tokens=5)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.bbox[0] >= 50.0
        assert c.bbox[2] <= 400.0
        assert c.token_count <= 512


def test_extract_overlap_prefix_sentence_and_word():
    text = "First sentence is concise. Second sentence is detailed and extensive. Third sentence concludes the thought."
    prefix = extract_overlap_prefix(text, overlap_tokens=15)
    assert "Third sentence concludes the thought." in prefix

    # Test word-level fallback on single run-on sentence
    long_single = "WordOne WordTwo WordThree WordFour WordFive WordSix WordSeven WordEight"
    word_prefix = extract_overlap_prefix(long_single, overlap_tokens=4)
    assert len(word_prefix.split()) >= 2

