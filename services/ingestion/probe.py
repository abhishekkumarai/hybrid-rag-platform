"""8-page heuristic layout prober using PyMuPDF (fitz).

Inspects up to 8 representative pages to classify documents into:
- 'fast_text': Standard digital single-column text (high throughput via PyMuPDF)
- 'layout': Multi-column, tables, or complex layout (Docling extraction)
- 'ocr': Scanned or image-dominated pages (RapidOCR extraction)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

from contracts.document import DocumentProfile
from services.common.logger import get_logger

logger = get_logger("ingestion.probe")


def select_sample_pages(total_pages: int, max_samples: int = 8) -> list[int]:
    """Selects up to max_samples page indices (1-indexed) across the document."""
    if total_pages <= max_samples:
        return list(range(1, total_pages + 1))

    # Pages: first 2, last 2, and evenly spaced interior pages
    first_pages = [1, 2]
    last_pages = [total_pages - 1, total_pages]
    interior_count = max_samples - len(first_pages) - len(last_pages)

    step = (total_pages - 3) / (interior_count + 1)
    interior = [int(2 + (i + 1) * step) for i in range(interior_count)]

    # Deduplicate and sort
    sampled = sorted(list(set(first_pages + interior + last_pages)))
    return sampled[:max_samples]


def probe_document(
    file_path: str | Path,
    text_coverage_threshold: float = 0.60,
    image_ratio_threshold: float = 0.65,
    gutter_gap_threshold_pt: float = 18.0,
) -> DocumentProfile:
    """Probes a PDF document and returns its computed DocumentProfile."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document file not found: {path}")

    doc = fitz.open(str(path))
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        return DocumentProfile(
            route="ocr",
            page_count=0,
            sample_pages=[],
            text_coverage=0.0,
            chars_per_page=0.0,
            image_ratio=0.0,
            columns=1,
            table_score=0.0,
            reason="Empty document",
        )

    sample_pages = select_sample_pages(total_pages, max_samples=8)
    logger.debug(f"Probing '{path.name}': {total_pages} total pages, sampled pages {sample_pages}")

    coverages: list[float] = []
    char_counts: list[int] = []
    image_ratios: list[float] = []
    column_counts: list[int] = []
    table_scores: list[float] = []

    for p_num in sample_pages:
        page = doc[p_num - 1]  # 0-indexed
        page_rect = page.rect
        page_area = max(page_rect.width * page_rect.height, 1.0)

        # 1. Text extraction & coverage
        text_page = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        text_area = 0.0
        total_chars = 0
        text_blocks: list[tuple[float, float, float, float]] = []

        for b in text_page:
            x0, y0, x1, y1, text, _, b_type = b
            if b_type == 0:  # Text block
                block_area = max(x1 - x0, 0) * max(y1 - y0, 0)
                text_area += block_area
                total_chars += len(text.strip())
                text_blocks.append((x0, y0, x1, y1))

        coverage = min(text_area / page_area, 1.0)
        coverages.append(coverage)
        char_counts.append(total_chars)

        # 2. Image area ratio
        images = page.get_images()
        img_area = 0.0
        for img_info in images:
            xref = img_info[0]
            for img_rect in page.get_image_rects(xref):
                img_area += max(img_rect.width * img_rect.height, 0)
        image_ratio = min(img_area / page_area, 1.0)
        image_ratios.append(image_ratio)

        # 3. Column detection (horizontal gap histogram)
        columns = 1
        if len(text_blocks) >= 2:
            # Sort by x0
            sorted_x = sorted(text_blocks, key=lambda b: b[0])
            for i in range(len(sorted_x) - 1):
                gap = sorted_x[i + 1][0] - sorted_x[i][2]
                if gap >= gutter_gap_threshold_pt:
                    # Check vertical overlap
                    y_overlap = min(sorted_x[i][3], sorted_x[i + 1][3]) - max(sorted_x[i][1], sorted_x[i + 1][1])
                    if y_overlap > 20.0:
                        columns = 2
                        break
        column_counts.append(columns)

        # 4. Table detection (drawing vector line density)
        drawings = page.get_drawings()
        lines_count = len([d for d in drawings if d.get("items")])
        table_score = min(lines_count / 25.0, 1.0)
        table_scores.append(table_score)

    doc.close()

    # Aggregate metrics across sampled pages
    avg_coverage = sum(coverages) / len(coverages)
    avg_chars = sum(char_counts) / len(char_counts)
    avg_img_ratio = sum(image_ratios) / len(image_ratios)
    max_columns = max(column_counts)
    avg_table_score = sum(table_scores) / len(table_scores)

    # Route decision logic
    route: Literal["fast_text", "layout", "ocr"]
    reason: str

    if avg_chars < 50 and avg_img_ratio > 0.40:
        route = "ocr"
        reason = f"Low character density ({avg_chars:.1f} chars/page) and high image content ({avg_img_ratio:.2%})"
    elif avg_coverage < text_coverage_threshold and avg_img_ratio > image_ratio_threshold:
        route = "ocr"
        reason = f"Scanned/image-dominated layout: text coverage {avg_coverage:.2%}, image ratio {avg_img_ratio:.2%}"
    elif avg_table_score > 0.35 or max_columns > 1:
        route = "layout"
        reason = f"Complex layout detected: columns={max_columns}, table_score={avg_table_score:.2f}"
    else:
        route = "fast_text"
        reason = f"Clean digital text: coverage={avg_coverage:.2%}, chars/page={avg_chars:.0f}"

    profile = DocumentProfile(
        route=route,
        page_count=total_pages,
        sample_pages=sample_pages,
        text_coverage=round(avg_coverage, 4),
        chars_per_page=round(avg_chars, 1),
        image_ratio=round(avg_img_ratio, 4),
        columns=max_columns,
        table_score=round(avg_table_score, 4),
        reason=reason,
    )

    logger.info(
        f"Probe completed for '{path.name}': route='{profile.route}', pages={total_pages}, reason='{profile.reason}'"
    )
    return profile
