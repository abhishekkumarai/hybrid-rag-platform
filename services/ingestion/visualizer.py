"""Visual PDF provenance renderer highlighting bounding boxes on document pages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

import fitz

from services.common.logger import get_logger

logger = get_logger("ingestion.visualizer")
DATA_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "documents"


def resolve_document_path(doc_identifier: str) -> Path | None:
    """Finds document file matching doc_id or file name, confined to data/documents/."""
    base = DATA_DOCS_DIR.resolve()

    clean_id = doc_identifier.strip()

    # 1. Direct match within data/documents/
    candidate = (base / clean_id).resolve()
    if candidate.is_relative_to(base) and candidate.is_file():
        return candidate

    candidate_pdf = (base / f"{clean_id}.pdf").resolve()
    if candidate_pdf.is_relative_to(base) and candidate_pdf.is_file():
        return candidate_pdf

    # 2. Normalize target identifier (strip .pdf and 8-hex hash suffix from _generate_doc_id)
    target_clean = clean_id.lower().replace(".pdf", "")
    target_no_hash = re.sub(r"_[0-9a-f]{8}$", "", target_clean)
    target_norm = re.sub(r"[^a-z0-9]", "", target_no_hash)

    pdf_files = list(base.glob("*.pdf"))

    # 3. Exact stem comparison with space/underscore/hyphen normalization
    for f in pdf_files:
        f_stem_lower = f.stem.lower()
        f_clean = f_stem_lower.replace(" ", "_").replace("-", "_")
        t_clean = target_clean.replace("-", "_")
        t_nh = target_no_hash.replace("-", "_")
        if f_clean == t_clean or f_clean == t_nh:
            return f

    # 4. Prefix, substring, and alphanumeric normalization matching
    for f in pdf_files:
        f_stem_lower = f.stem.lower()
        f_clean = f_stem_lower.replace(" ", "_").replace("-", "_")
        t_clean = target_clean.replace("-", "_")
        if f_clean in t_clean or t_clean.startswith(f_clean):
            return f
        f_norm = re.sub(r"[^a-z0-9]", "", f_stem_lower)
        if f_norm and (f_norm == target_norm or target_norm.startswith(f_norm) or f_norm in target_norm):
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
