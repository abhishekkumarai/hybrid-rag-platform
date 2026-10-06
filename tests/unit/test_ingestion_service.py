"""Unit test for IngestionService API."""

from pathlib import Path

import fitz
import pytest

from contracts.document import BlockType, IngestRequest
from services.ingestion.service import IngestionService


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "annual_report.pdf"
    doc = fitz.open()

    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((72, 72), "Annual Financial Report 2026", fontsize=20)
    page1.insert_text((72, 120), "Total revenue increased by 25% year-over-year.", fontsize=11)

    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 72), "Operating Expenses and Guidance", fontsize=16)
    page2.insert_text((72, 110), "Operating cash flow remains healthy with strong balance sheet.", fontsize=11)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_ingestion_service_digital_flow(sample_pdf: Path):
    service = IngestionService()
    req = IngestRequest(file_path=str(sample_pdf))
    res = service.parse(req)

    assert res.doc_id.startswith("annual_report_")
    assert res.profile.route == "fast_text"  # probe verdict; the service then upgrades it to Docling
    assert len(res.blocks) >= 2
    assert res.duration_ms > 0

    # Verify heading was detected by font size
    headings = [b for b in res.blocks if b.type == BlockType.HEADING]
    assert len(headings) >= 1
    assert "Annual Financial Report" in headings[0].text
    assert headings[0].page == 1
    assert len(headings[0].bbox) == 4


def test_ingestion_service_override(sample_pdf: Path):
    service = IngestionService()
    req = IngestRequest(file_path=str(sample_pdf), profile_override="layout")
    res = service.parse(req)

    assert res.doc_id.startswith("annual_report_")
    assert len(res.blocks) >= 1


def test_digital_pdf_routes_to_docling_by_default(sample_pdf: Path, monkeypatch):
    """IRA-61: a clean digital PDF (probe says fast_text) is parsed by the layout/Docling parser."""
    service = IngestionService()
    called = {}

    def fake_layout(path, doc_id):
        called["layout"] = True
        return []

    monkeypatch.setattr(service.layout_parser, "parse", fake_layout)
    service.parse(IngestRequest(file_path=str(sample_pdf)))
    assert called.get("layout")


def test_docling_default_can_be_disabled(sample_pdf: Path, monkeypatch):
    from services.common.config import load_config

    cfg = load_config()
    cfg.ingestion.docling_default = False
    monkeypatch.setattr("services.ingestion.service.load_config", lambda: cfg)
    service = IngestionService()
    monkeypatch.setattr(
        service.layout_parser, "parse", lambda *a: pytest.fail("layout parser must not run")
    )
    service.parse(IngestRequest(file_path=str(sample_pdf)))
