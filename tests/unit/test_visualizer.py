"""Unit tests for the PDF visual provenance renderer and /api/v1/preview endpoint."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from services.gateway.api import app
from services.ingestion.visualizer import render_page_with_bbox

client = TestClient(app)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "provenance_test_doc.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Visual Provenance Test Document", fontsize=16)
    page.insert_text((72, 120), "Highlighted bounding box target area.", fontsize=12)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_render_page_with_bbox(sample_pdf: Path):
    png_bytes = render_page_with_bbox(
        file_path=sample_pdf,
        page_num=1,
        bbox=(72.0, 110.0, 300.0, 135.0),
        zoom=1.0,
    )
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 1000
    # PNG Magic bytes: \x89PNG\r\n\x1a\n
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_page_missing_file():
    with pytest.raises(FileNotFoundError):
        render_page_with_bbox("non_existent_file.pdf", page_num=1)


def test_gateway_preview_endpoint(sample_pdf: Path):
    # Copy to data/documents for resolve_document_path
    dest = Path("data/documents") / "provenance_test_doc.pdf"
    dest.write_bytes(sample_pdf.read_bytes())

    try:
        response = client.get(
            "/api/v1/preview?doc_id=provenance_test_doc.pdf&page=1&x0=72&y0=110&x1=300&y1=135"
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        if dest.exists():
            dest.unlink()


def test_gateway_preview_missing_doc():
    response = client.get("/api/v1/preview?doc_id=does_not_exist.pdf")
    assert response.status_code == 404
