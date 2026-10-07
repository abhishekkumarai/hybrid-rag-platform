"""Unit tests for layout-aware document parsing and semantic hierarchy chunking (IRA-61, IRA-64)."""

from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

from contracts.document import BlockType
from services.indexing.chunker import chunk_blocks
from services.ingestion.parsers.layout import LayoutParser


@pytest.fixture
def structured_pdf(tmp_path: Path) -> Path:
    """Creates a sample multi-page PDF with clear titles, subheadings, and paragraphs."""
    pdf_path = tmp_path / "executive_brief.pdf"
    doc = fitz.open()

    # Page 1: Main Title + Paragraph
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((72, 72), "Executive Architecture Brief", fontsize=22)
    page1.insert_text(
        (72, 120),
        "The distributed platform coordinates hybrid dense vector retrieval and sparse keyword search.",
        fontsize=11,
    )

    # Page 2: Subheading + Paragraph
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 72), "Retrieval Optimization Guidelines", fontsize=16)
    page2.insert_text(
        (72, 110),
        "FlashRank cross-encoder reranking scores top candidates to optimize reciprocal rank fusion precision.",
        fontsize=11,
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_layout_parser_extracts_headings_and_subheadings(structured_pdf: Path):
    """Verifies that LayoutParser detects both H1 and H2 headers instead of flattening to text."""
    parser = LayoutParser()
    blocks = parser.parse(str(structured_pdf), "exec_brief")

    assert len(blocks) >= 2

    headings = [b for b in blocks if b.type == BlockType.HEADING]
    assert len(headings) >= 1, "At least one heading should be classified"

    first_h = headings[0]
    assert "Executive Architecture Brief" in first_h.text
    assert first_h.page == 1
    assert len(first_h.bbox) == 4
    assert first_h.level in (1, 2)


def test_layout_parser_hierarchical_chunking(structured_pdf: Path):
    """Verifies that blocks from LayoutParser produce breadcrumb-enriched chunks."""
    parser = LayoutParser()
    blocks = parser.parse(str(structured_pdf), "exec_brief")
    chunks = chunk_blocks(blocks, "exec_brief", max_tokens=512)

    assert len(chunks) >= 1
    # Find text chunks (excluding any initial decorative picture blocks detected by Docling)
    text_chunks = [c for c in chunks if not c.is_figure and not c.is_table]
    assert len(text_chunks) >= 1
    target_chunk = text_chunks[0]

    # Verify heading is retained in chunk metadata
    assert len(target_chunk.headings) >= 1
    assert "Executive Architecture Brief" in target_chunk.headings[0]
    assert "Section: Executive Architecture Brief" in target_chunk.text
    assert len(target_chunk.bbox) == 4
    assert target_chunk.token_count <= 512


def test_layout_parser_fallback_on_docling_error(structured_pdf: Path):
    """Verifies that LayoutParser falls back to font-size-aware PyMuPDF if Docling fails."""
    parser = LayoutParser()
    with patch.object(parser, "_parse_with_docling", side_effect=RuntimeError("Simulated failure")):
        blocks = parser.parse(str(structured_pdf), "exec_brief")

    assert len(blocks) >= 2
    # Verify fallback still captured the font-size heading
    headings = [b for b in blocks if b.type == BlockType.HEADING]
    assert len(headings) >= 1
    assert "Executive Architecture Brief" in headings[0].text
    assert headings[0].level in (1, 2)
    assert len(headings[0].bbox) == 4


def test_text_in_bbox_recovers_title_text(structured_pdf: Path):
    """IRA-61: text Docling mislabels as a picture is recovered from the PDF text layer."""
    text = LayoutParser._text_in_bbox(structured_pdf, 1, (60.0, 50.0, 400.0, 80.0))
    assert "Executive Architecture Brief" in text
    assert LayoutParser._text_in_bbox(structured_pdf, 1, (0.0, 0.0, 0.0, 0.0)) == ""
    assert LayoutParser._text_in_bbox(structured_pdf, 9, (0.0, 0.0, 100.0, 100.0)) == ""


def test_rejoin_drop_cap_is_generic():
    from services.ingestion.parsers.layout import _rejoin_drop_cap

    assert _rejoin_drop_cap("T hink about someone you know") == "Think about someone you know"
    assert _rejoin_drop_cap("P lutarch, a Roman") == "Plutarch, a Roman"
    # Legitimate one-letter words and normal prose are untouched.
    assert _rejoin_drop_cap("A lot of people agree") == "A lot of people agree"
    assert _rejoin_drop_cap("I am here") == "I am here"
    assert _rejoin_drop_cap("The cat") == "The cat"
    assert _rejoin_drop_cap("T 5 items") == "T 5 items"
