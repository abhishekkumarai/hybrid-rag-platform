"""IRA-67: pptx, image and text sources through the real pipeline — conversion, parsing (real OCR /
Docling / LibreOffice), indexing and retrieval with a citation. Nothing is mocked; a format whose
external tool is missing is skipped, not faked."""

from pathlib import Path

import fitz
import pytest

from contracts.document import IngestRequest
from contracts.retrieval import SearchQuery
from services.indexing.service import IndexingService
from services.ingestion import normalize
from services.ingestion.service import IngestionService
from services.retrieval.service import RetrievalService


@pytest.fixture(autouse=True)
def converted_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CONVERTED_DIR", tmp_path / "converted")


def _roundtrip(src: Path, tmp_path: Path, question: str):
    ingestion = IngestionService()
    indexing = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    retrieval = RetrievalService(qdrant_store=indexing.qdrant, bm25_store=indexing.bm25)

    ingested = ingestion.parse(IngestRequest(file_path=str(src)))
    assert ingested.error is None and ingested.blocks, ingested.error
    assert indexing.chunk_and_index(doc_id=ingested.doc_id, blocks=ingested.blocks).indexed_count >= 1

    res = retrieval.retrieve(SearchQuery(query_text=question, top_k=10, top_rerank=3, min_rerank_score=0.15))
    assert not res.refused
    assert res.citations and len(res.citations[0].bbox) == 4
    return ingested, res


def test_markdown_file_is_retrievable_with_citation(tmp_path):
    src = tmp_path / "field_notes.md"
    src.write_text(
        "# Field Notes\n\nThe peregrine falcon nests on north-facing cliff ledges every spring.\n\n"
        "## Diet\n\nFalcons hunt pigeons and shorebirds in open country.\n",
        "utf-8",
    )
    ingested, res = _roundtrip(src, tmp_path, "Where does the peregrine falcon nest?")
    assert "cliff ledges" in res.candidates[0].text
    assert res.citations[0].page == 1
    # the citation's document opens as a page image with the bbox drawn on it
    from services.ingestion.visualizer import render_page_with_bbox

    png = render_page_with_bbox(ingested.file_path, 1, res.citations[0].bbox)
    assert png.startswith(b"\x89PNG")


def test_image_is_ocrd_and_retrievable(tmp_path):
    page = fitz.open()
    p = page.new_page(width=900, height=300)
    p.insert_text((40, 80), "The harbour lighthouse was built in 1887 by Thomas Alder.", fontsize=22)
    p.insert_text((40, 140), "Its lamp could be seen from forty kilometres out to sea.", fontsize=22)
    png = tmp_path / "plaque.png"
    p.get_pixmap(dpi=200).save(str(png))
    page.close()

    ingested, res = _roundtrip(png, tmp_path, "Who built the harbour lighthouse?")
    assert ingested.profile.route in ("ocr", "paddleocr")
    assert "Alder" in res.candidates[0].text


def _soffice_works() -> bool:
    return normalize._find_soffice() is not None


@pytest.mark.skipif(not _soffice_works(), reason="LibreOffice not installed")
def test_pptx_is_retrievable_with_slide_citation(tmp_path):
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for title, body in (("Quarterly Plan", "Revenue target is twelve million dollars."),
                        ("Hiring", "We will recruit four backend engineers in Berlin.")):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    src = tmp_path / "plan.pptx"
    prs.save(str(src))

    ingested, res = _roundtrip(src, tmp_path, "Where will the backend engineers be recruited?")
    assert "Berlin" in res.candidates[0].text
    assert res.citations[0].page == 2
