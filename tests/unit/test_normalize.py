"""IRA-67: pptx, image and text sources are converted to PDF so the PDF pipeline can ingest them."""

from pathlib import Path

import fitz
import pytest

from contracts.document import IngestRequest
from services.ingestion import normalize
from services.ingestion.normalize import ConversionError, is_supported, to_pdf
from services.ingestion.service import IngestionService


@pytest.fixture(autouse=True)
def converted_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "CONVERTED_DIR", tmp_path / "converted")


def _png(path: Path) -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    pix.clear_with(255)
    pix.save(str(path))
    return path


def _text_of(pdf: Path) -> str:
    with fitz.open(str(pdf)) as doc:
        return "\n".join(p.get_text() for p in doc)


def test_supported_extensions():
    for name in ("a.pdf", "a.PPTX", "a.txt", "a.md", "a.png", "a.jpg", "a.jpeg"):
        assert is_supported(name)
    assert not is_supported("a.docx")
    assert not is_supported("a.exe")


def test_scheduler_allow_list_matches_converters():
    from services.scheduling.registry import SUPPORTED_EXTENSIONS

    assert SUPPORTED_EXTENSIONS == normalize.SUPPORTED_EXTENSIONS


def test_pdf_is_returned_unchanged(tmp_path):
    pdf = tmp_path / "a.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.save(str(pdf))
    assert to_pdf(pdf, "a_1") == pdf


def test_text_file_becomes_text_layer_pdf(tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("Stoics held that virtue is sufficient for happiness.\n\nSecond paragraph.", "utf-8")
    out = to_pdf(src, "notes_1")
    assert out.suffix == ".pdf" and out != src
    assert "virtue is su" in _text_of(out)  # "ffi" may be a ligature glyph; the service expands it


def test_markdown_headings_render_larger_than_body(tmp_path):
    src = tmp_path / "guide.md"
    src.write_text("# Retrieval Guide\n\nBody paragraph text.\n\n- first item\n- second item\n", "utf-8")
    out = to_pdf(src, "guide_1")
    with fitz.open(str(out)) as doc:
        sizes = {}
        for b in doc[0].get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                for span in line["spans"]:
                    sizes[span["text"].strip()] = span["size"]
    assert sizes["Retrieval Guide"] > sizes["Body paragraph text."]
    assert "second item" in _text_of(out)


def test_long_text_spans_multiple_pages(tmp_path):
    src = tmp_path / "long.txt"
    src.write_text("\n\n".join(f"Paragraph {i} " + "word " * 80 for i in range(60)), "utf-8")
    with fitz.open(str(to_pdf(src, "long_1"))) as doc:
        assert len(doc) > 1


def test_empty_text_file_is_rejected(tmp_path):
    src = tmp_path / "empty.txt"
    src.write_text("  \n", "utf-8")
    with pytest.raises(ConversionError):
        to_pdf(src, "empty_1")


def test_image_becomes_one_page_pdf(tmp_path):
    out = to_pdf(_png(tmp_path / "scan.png"), "scan_1")
    with fitz.open(str(out)) as doc:
        assert len(doc) == 1


def test_conversion_is_cached(tmp_path):
    src = tmp_path / "n.txt"
    src.write_text("hello world", "utf-8")
    first = to_pdf(src, "n_1")
    mtime = first.stat().st_mtime_ns
    assert to_pdf(src, "n_1") == first and first.stat().st_mtime_ns == mtime


def test_unsupported_type_raises(tmp_path):
    src = tmp_path / "a.docx"
    src.write_bytes(b"x")
    with pytest.raises(ConversionError):
        to_pdf(src, "a_1")


def test_pptx_without_libreoffice_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(normalize, "_find_soffice", lambda: None)
    src = tmp_path / "deck.pptx"
    src.write_bytes(b"x")
    with pytest.raises(ConversionError, match="LibreOffice"):
        to_pdf(src, "deck_1")


needs_soffice = pytest.mark.skipif(normalize._find_soffice() is None, reason="LibreOffice not installed")


def _real_pptx(path: Path) -> Path:
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for title, body in (("Falcon Migration", "Peregrine falcons winter on the coast."),
                        ("Nesting Habits", "Nests are built on north-facing cliff ledges.")):
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    prs.save(str(path))
    return path


@needs_soffice
def test_real_pptx_converts_one_page_per_slide(tmp_path):
    out = to_pdf(_real_pptx(tmp_path / "deck.pptx"), "deck_1")
    with fitz.open(str(out)) as doc:
        assert len(doc) == 2
    text = " ".join(_text_of(out).split())  # PDF line wraps are not part of the content
    assert "Falcon Migration" in text and "cliff ledges" in text


@needs_soffice
def test_corrupt_pptx_is_reported(tmp_path):
    src = tmp_path / "broken.pptx"
    src.write_bytes(b"this is not a presentation")
    with pytest.raises(ConversionError):
        to_pdf(src, "broken_1")


@needs_soffice
def test_real_pptx_ingests_with_slide_pages_and_bboxes(tmp_path):
    res = IngestionService().parse(IngestRequest(file_path=str(_real_pptx(tmp_path / "deck.pptx"))))
    assert {b.page for b in res.blocks} == {1, 2}
    assert any("cliff ledges" in b.text for b in res.blocks)
    assert all(b.bbox[2] > b.bbox[0] for b in res.blocks if b.type.value == "text")


def test_ingestion_parses_text_file_end_to_end(tmp_path):
    src = tmp_path / "Field Notes.md"
    src.write_text("# Field Notes\n\nThe falcon nests on the north ridge every spring.\n", "utf-8")
    res = IngestionService().parse(IngestRequest(file_path=str(src)))
    assert res.doc_id.startswith("field_notes_")
    assert res.file_path.endswith(f"{res.doc_id}.pdf")  # previews/raw open the converted PDF
    assert any("falcon" in b.text for b in res.blocks)
    assert all(len(b.bbox) == 4 and b.page >= 1 for b in res.blocks)


def test_doc_id_comes_from_the_original_file(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("same content", "utf-8")
    svc = IngestionService()
    assert svc.parse(IngestRequest(file_path=str(src))).doc_id == svc._generate_doc_id(src)
