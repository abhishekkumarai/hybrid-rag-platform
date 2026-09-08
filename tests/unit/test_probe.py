"""Unit test for 8-page heuristic layout probe."""

from pathlib import Path

import fitz

from services.ingestion.probe import probe_document, select_sample_pages


def test_select_sample_pages():
    # Less than 8 pages -> all pages
    assert select_sample_pages(5, max_samples=8) == [1, 2, 3, 4, 5]

    # Exactly 8 pages -> all pages
    assert select_sample_pages(8, max_samples=8) == [1, 2, 3, 4, 5, 6, 7, 8]

    # 100 pages -> max 8 pages, including first 2 and last 2
    sampled = select_sample_pages(100, max_samples=8)
    assert len(sampled) <= 8
    assert 1 in sampled
    assert 2 in sampled
    assert 99 in sampled
    assert 100 in sampled


def test_probe_clean_digital_pdf(tmp_path: Path):
    pdf_path = tmp_path / "digital.pdf"
    doc = fitz.open()

    # Create 3 pages with abundant digital text
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        text = f"Chapter {i+1}: Standard Single Column Text\n" + ("This is clean digital text with standard font. " * 30)
        page.insert_text((72, 72), text, fontsize=12)

    doc.save(str(pdf_path))
    doc.close()

    profile = probe_document(pdf_path)
    assert profile.page_count == 3
    assert profile.route == "fast_text"
    assert profile.text_coverage > 0.0
    assert profile.chars_per_page > 100
