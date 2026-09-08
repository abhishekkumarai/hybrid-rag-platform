"""Unit tests verifying all Langflow custom components."""

from pathlib import Path

import fitz
import pytest

from components.citation_formatter import CitationFormatterComponent
from components.layout_probe import LayoutProbeComponent


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "langflow_test.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Architecture Verification", fontsize=18)
    page.insert_text((72, 110), "Langflow connects the SOA services together on port 7860.", fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_layout_probe_component(sample_pdf: Path):
    probe_comp = LayoutProbeComponent()
    blocks = probe_comp.extract_blocks(file_path=str(sample_pdf))
    assert len(blocks) >= 2
    assert blocks[0]["text"] == "Architecture Verification"

    route_info = probe_comp.get_route_info(file_path=str(sample_pdf))
    assert route_info["route"] == "fast_text"


def test_citation_formatter_component():
    formatter = CitationFormatterComponent()
    raw_answer = "The architecture connects on port 7860."
    citations = [
        {
            "formatted_badge": "[doc1: Page 1, (72.0, 72.0, 540.0, 120.0)]",
            "snippet": "Langflow connects the SOA services together on port 7860.",
        }
    ]

    res = formatter.format_response(answer_text=raw_answer, citations=citations)
    assert raw_answer in res
    assert "Verified Sources & Provenance" in res
    assert "[doc1: Page 1, (72.0, 72.0, 540.0, 120.0)]" in res
