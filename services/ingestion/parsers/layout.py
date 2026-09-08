"""Layout-aware multimodal parser for tables, figures, and multi-column documents.

Extracts:
1. Tables as structured Markdown with captions, headers, and exact cell coordinates.
2. Figures and diagrams rendered as high-res PNG crops with contextual captions.
3. Multi-column text with heading hierarchy and bounding box provenance.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from contracts.document import Block, BlockType
from services.common.logger import get_logger
from services.ingestion.multimodal import MultimodalExtractor

logger = get_logger("ingestion.layout")


class LayoutParser:
    """Extracts tables, figures, and text with bounding box provenance."""

    def __init__(self) -> None:
        self.multimodal_extractor = MultimodalExtractor()

    def parse(self, file_path: str, doc_id: str) -> list[Block]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        doc = fitz.open(str(path))
        blocks: list[Block] = []

        # 1. Extract Multimodal Elements (Tables & Figures)
        mm_blocks, occupied_bboxes = self.multimodal_extractor.extract_tables_and_figures(doc, doc_id)
        blocks.extend(mm_blocks)

        # 2. Extract remaining text blocks (skipping table and figure areas)
        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            order = 1000 + p_idx * 100  # Offset order for text blocks

            page_blocks = page.get_text("blocks")
            for b in page_blocks:
                x0, y0, x1, y1, text, _, b_type = b
                if b_type != 0 or not text.strip():
                    continue

                b_rect = fitz.Rect(x0, y0, x1, y1)

                # Skip if block is inside or significantly overlaps an extracted table or figure
                inside_mm = any(
                    b_rect.intersects(fitz.Rect(*ob)) and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                    for ob in occupied_bboxes
                )
                if inside_mm:
                    continue

                # Check if this block is a heading based on font or characteristics
                cleaned_text = text.strip()
                classification = BlockType.TEXT
                level: int | None = None
                if len(cleaned_text.splitlines()) <= 2 and len(cleaned_text) < 80:
                    if cleaned_text.isupper() or cleaned_text.startswith("#"):
                        classification = BlockType.HEADING
                        level = 1 if cleaned_text.isupper() else 2

                block_id = f"{doc_id}_p{p_num}_txt_{order}"
                blocks.append(
                    Block(
                        id=block_id,
                        doc_id=doc_id,
                        page=p_num,
                        bbox=(float(x0), float(y0), float(x1), float(y1)),
                        type=classification,
                        text=cleaned_text,
                        level=level,
                        order=order,
                    )
                )
                order += 1

        doc.close()
        # Sort blocks chronologically by page then vertical position y0
        blocks.sort(key=lambda b: (b.page, b.bbox[1]))
        logger.info(
            f"LayoutParser: extracted {len(blocks)} total blocks "
            f"({len(mm_blocks)} multimodal, {len(blocks) - len(mm_blocks)} text) from '{path.name}'"
        )
        return blocks
