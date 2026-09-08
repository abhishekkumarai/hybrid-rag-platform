"""Unit test for content-aware chunker."""

from contracts.document import Block, BlockType
from services.indexing.chunker import chunk_blocks, split_large_table


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
