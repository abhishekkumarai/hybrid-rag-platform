"""Visual PDF provenance renderer highlighting bounding boxes on document pages."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import fitz

from services.common.logger import get_logger

logger = get_logger("ingestion.visualizer")
DATA_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "documents"


def resolve_document_path(doc_identifier: str) -> Path | None:
    """Finds document file matching doc_id or file name in data/documents/."""
    # 1. Direct path check
    direct = Path(doc_identifier)
    if direct.exists() and direct.is_file():
        return direct

    # 2. Check within data/documents
    candidate = DATA_DOCS_DIR / doc_identifier
    if candidate.exists() and candidate.is_file():
        return candidate

    # 3. Fuzzy search by stem or prefix
    target_clean = doc_identifier.lower().replace(".pdf", "")
    for f in DATA_DOCS_DIR.glob("*.pdf"):
        if target_clean in f.name.lower() or f.stem.lower() in target_clean:
            return f

    return None


def render_page_with_bbox(
    file_path: Path | str,
    page_num: int,
    bbox: Tuple[float, float, float, float] | None = None,
    zoom: float = 1.5,
) -> bytes:
    """Renders a PDF page to PNG bytes with an optional highlighted bounding box overlay."""
    doc_path = Path(file_path)
    if not doc_path.exists():
        raise FileNotFoundError(f"Document file not found: {doc_path}")

    doc = fitz.open(str(doc_path))
    try:
        page_idx = max(0, min(page_num - 1, len(doc) - 1))
        page = doc[page_idx]

        if bbox and len(bbox) == 4:
            x0, y0, x1, y1 = bbox
            # Ensure valid non-inverted coordinates
            rect = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            try:
                page.draw_rect(
                    rect,
                    color=(0.15, 0.45, 0.95),  # Vibrant blue border
                    fill=(0.25, 0.55, 1.0),    # Soft blue fill
                    fill_opacity=0.25,
                    width=2.5,
                )
            except Exception as e:
                logger.warning(f"Could not draw bbox highlight {bbox}: {e}")

        # Scale for crisp browser preview
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
