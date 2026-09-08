"""High-speed text and multimodal parser using PyMuPDF (fitz).

Extracts blocks from digital PDFs with bounding boxes, font-size-based heading
detection, deep table recognition, and figure crops.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from contracts.document import Block, BlockType
from services.common.logger import get_logger
from services.ingestion.multimodal import MultimodalExtractor

logger = get_logger("ingestion.fast_text")


class FastTextParser:
    """Extracts digital text, headings, tables, and figures directly via PyMuPDF."""

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

        # 2. Extract Text and Headings via Dict
        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            page_dict = page.get_text("dict")
            order = 0

            for b in page_dict.get("blocks", []):
                b_type = b.get("type", 0)
                bbox = tuple(b.get("bbox", (0.0, 0.0, 0.0, 0.0)))
                b_rect = fitz.Rect(*bbox)

                # Skip if text is inside an extracted table or figure
                if occupied_bboxes and any(
                    b_rect.intersects(fitz.Rect(*ob)) and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                    for ob in occupied_bboxes
                ):
                    continue

                if b_type == 0:  # Text block
                    lines = b.get("lines", [])
                    block_text_parts: list[str] = []
                    max_size = 0.0
                    is_bold = False

                    for line in lines:
                        line_text_parts: list[str] = []
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            if text:
                                line_text_parts.append(text)
                                size = span.get("size", 10.0)
                                if size > max_size:
                                    max_size = size
                                flags = span.get("flags", 0)
                                if flags & 2 or "bold" in span.get("font", "").lower():
                                    is_bold = True
                        if line_text_parts:
                            block_text_parts.append(" ".join(line_text_parts))

                    block_text = "\n".join(block_text_parts).strip()
                    if not block_text:
                        continue

                    # Classify heading based on font size & bold
                    classification = BlockType.TEXT
                    level: int | None = None

                    if max_size >= 16.0 or (max_size >= 14.0 and is_bold):
                        classification = BlockType.HEADING
                        level = 1 if max_size >= 18.0 else 2
                    elif max_size >= 12.5 and is_bold:
                        classification = BlockType.HEADING
                        level = 3

                    block_id = f"{doc_id}_p{p_num}_b{order}"
                    blocks.append(
                        Block(
                            id=block_id,
                            doc_id=doc_id,
                            page=p_num,
                            bbox=bbox,
                            type=classification,
                            text=block_text,
                            level=level,
                            order=order,
                            meta={"font_size": max_size, "is_bold": is_bold},
                        )
                    )
                    order += 1

        page_count = len(doc)
        doc.close()
        # Sort blocks chronologically by page then vertical position
        blocks.sort(key=lambda b: (b.page, b.bbox[1]))
        logger.info(
            f"FastTextParser: parsed {len(blocks)} blocks ({len(mm_blocks)} multimodal) from '{path.name}' across {page_count} pages"
        )
        return blocks
