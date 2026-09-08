"""Unit tests for multimodal deep table and figure extraction."""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from contracts.document import Block, BlockType
from services.gateway.api import app
from services.indexing.chunker import chunk_blocks
from services.ingestion.multimodal import MultimodalExtractor

client = TestClient(app)


def test_multimodal_block_and_chunk_contracts():
    block_table = Block(
        id="doc_t1",
        doc_id="test_doc",
        page=1,
        bbox=(50.0, 100.0, 500.0, 300.0),
        type=BlockType.TABLE,
        text="| Col1 | Col2 |\n|---|---|\n| A | B |",
        caption="Table 1: Benchmark Matrix",
        order=0,
    )
    assert block_table.type == BlockType.TABLE
    assert block_table.caption == "Table 1: Benchmark Matrix"

    block_fig = Block(
        id="doc_f1",
        doc_id="test_doc",
        page=2,
        bbox=(50.0, 150.0, 500.0, 400.0),
        type=BlockType.IMAGE,
        text="Figure 1: Architecture Overview",
        caption="Figure 1: Architecture Overview",
        image_path="data/figures/test_doc_p2_fig_0.png",
        order=1,
    )
    assert block_fig.type == BlockType.IMAGE
    assert block_fig.image_path == "data/figures/test_doc_p2_fig_0.png"

    # Test chunking of multimodal blocks
    chunks = chunk_blocks([block_table, block_fig], doc_id="test_doc")
    assert len(chunks) == 2
    assert chunks[0].is_table is True
    assert chunks[0].is_figure is False
    assert chunks[1].is_table is False
    assert chunks[1].is_figure is True
    assert chunks[1].image_path == "data/figures/test_doc_p2_fig_0.png"


def test_multimodal_extractor_with_fixture():
    pdf_path = Path("data/documents/multimodal_hardware_benchmark.pdf")
    if not pdf_path.exists():
        pytest.skip("Test PDF fixture not present")

    doc = fitz.open(str(pdf_path))
    extractor = MultimodalExtractor()
    blocks, bboxes = extractor.extract_tables_and_figures(doc, "benchmark_doc")
    doc.close()

    assert len(blocks) >= 2
    table_blocks = [b for b in blocks if b.type == BlockType.TABLE]
    figure_blocks = [b for b in blocks if b.type == BlockType.IMAGE]

    assert len(table_blocks) >= 1
    assert "RTX 3050" in table_blocks[0].text
    assert table_blocks[0].caption is not None

    assert len(figure_blocks) >= 1
    assert figure_blocks[0].image_path is not None
    assert Path(figure_blocks[0].image_path).exists()


def test_gateway_figure_serving():
    # Verify figure endpoint
    figures_dir = Path("data/figures")
    figures_dir.mkdir(parents=True, exist_ok=True)
    dummy_fig = figures_dir / "unit_test_dummy_fig.png"
    dummy_fig.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")

    try:
        resp = client.get("/api/v1/figures/unit_test_dummy_fig.png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

        # Nonexistent figure returns 404
        resp_404 = client.get("/api/v1/figures/nonexistent_fig.png")
        assert resp_404.status_code == 404
    finally:
        if dummy_fig.exists():
            dummy_fig.unlink()
