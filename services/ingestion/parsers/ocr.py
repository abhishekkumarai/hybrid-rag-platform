"""OCR parser for scanned documents and image-only pages."""

from __future__ import annotations

import os
from pathlib import Path

import fitz

from contracts.document import Block, BlockType
from services.common.logger import get_logger

logger = get_logger("ingestion.ocr")


class OCRParser:
    """Extracts text from scanned pages using OCR."""

    def __init__(self) -> None:
        tesseract_cmd = os.environ.get("TESSERACT_CMD")
        if tesseract_cmd and Path(tesseract_cmd).exists():
            fitz.TOOLS.set_small_glyph_heights(False)

    def parse(self, file_path: str, doc_id: str) -> list[Block]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        doc = fitz.open(str(path))
        blocks: list[Block] = []

        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            order = 0

            # Try PyMuPDF native OCR textpage
            try:
                textpage = page.get_textpage_ocr(language="eng", dpi=150)
                ocr_blocks = textpage.extractBLOCKS()
                for b in ocr_blocks:
                    x0, y0, x1, y1, text, _, b_type = b
                    if text.strip():
                        block_id = f"{doc_id}_p{p_num}_b{order}"
                        blocks.append(
                            Block(
                                id=block_id,
                                doc_id=doc_id,
                                page=p_num,
                                bbox=(x0, y0, x1, y1),
                                type=BlockType.TEXT,
                                text=text.strip(),
                                order=order,
                                meta={"source": "ocr"},
                            )
                        )
                        order += 1
            except Exception as e:
                logger.warning(f"OCR failed on page {p_num} of '{path.name}', falling back to standard extraction: {e}")
                # Fallback to standard text blocks
                for b in page.get_text("blocks"):
                    x0, y0, x1, y1, text, _, b_type = b
                    if text.strip():
                        block_id = f"{doc_id}_p{p_num}_b{order}"
                        blocks.append(
                            Block(
                                id=block_id,
                                doc_id=doc_id,
                                page=p_num,
                                bbox=(x0, y0, x1, y1),
                                type=BlockType.TEXT,
                                text=text.strip(),
                                order=order,
                            )
                        )
                        order += 1

        doc.close()
        logger.info(f"OCRParser: extracted {len(blocks)} blocks from '{path.name}'")
        return blocks
