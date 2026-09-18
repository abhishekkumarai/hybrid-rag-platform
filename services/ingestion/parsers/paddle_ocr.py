"""PaddleOCR parser for high-accuracy document text and layout extraction (REC-61).

Integrates PaddleOCR (https://github.com/PADDLEPADDLE/PADDLEOCR) as a document
ingestion route with PyMuPDF rasterization, bounding box normalization to 72dpi PDF points,
and robust fallback when PaddleOCR is unavailable or fails on specific pages.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import fitz
import numpy as np

from contracts.document import Block, BlockType
from services.common.logger import get_logger
from services.ingestion.multimodal import MultimodalExtractor

# Bypass remote model connectivity checks on local inference
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

logger = get_logger("ingestion.paddle_ocr")


class PaddleOCRParser:
    """Extracts text and layout blocks using PaddleOCR with PyMuPDF rendering."""

    def __init__(
        self,
        lang: str = "en",
        use_textline_orientation: bool = True,
        use_angle_cls: bool | None = None,
        dpi: int = 150,
        confidence_threshold: float = 0.40,
    ) -> None:
        self.lang = lang
        self.use_textline_orientation = (
            use_angle_cls if use_angle_cls is not None else use_textline_orientation
        )
        self.use_angle_cls = self.use_textline_orientation
        self.dpi = dpi
        self.confidence_threshold = confidence_threshold
        self.multimodal_extractor = MultimodalExtractor()
        self._engine: Any = None
        self._initialized: bool = False
        self._available: bool = False

    def is_available(self) -> bool:
        """Checks if PaddleOCR is installed and successfully loadable."""
        if not self._initialized:
            self._init_engine()
        return self._available

    def _init_engine(self) -> None:
        """Lazily initializes the PaddleOCR inference engine."""
        self._initialized = True
        try:
            from paddleocr import PaddleOCR

            # Initialize PaddleOCR engine
            self._engine = PaddleOCR(
                lang=self.lang,
                use_textline_orientation=self.use_textline_orientation,
            )
            self._available = True
            logger.info(f"PaddleOCR initialized successfully with lang='{self.lang}', orientation={self.use_textline_orientation}")
        except Exception as e:
            self._available = False
            self._engine = None
            logger.warning(
                f"PaddleOCR is not available ({e}). Ingestion will fall back to native OCR / text extraction."
            )

    def parse(self, file_path: str, doc_id: str) -> list[Block]:
        """Parses a document using PaddleOCR across all pages with multimodal figure/table extraction."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        doc = fitz.open(str(path))
        blocks: list[Block] = []

        # 1. Extract figures and tables across all pages first to avoid OCR duplication
        mm_blocks, occupied_bboxes = self.multimodal_extractor.extract_tables_and_figures(doc, doc_id)

        # 2. Check engine availability
        engine_ready = self.is_available()

        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            order = 0
            page_occupied = (
                occupied_bboxes.get(p_num, [])
                if isinstance(occupied_bboxes, dict)
                else []
            )

            page_blocks: list[Block] = []

            if engine_ready and self._engine is not None:
                try:
                    # Render page to raster bitmap for PaddleOCR
                    pix = page.get_pixmap(dpi=self.dpi)
                    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                    if pix.n == 4:  # RGBA -> RGB
                        img = img[:, :, :3]

                    # Run PaddleOCR inference
                    ocr_results = self._engine.ocr(img)

                    # PaddleOCR returns a list of detections for each image: [[[box_pts], (text, conf)], ...]
                    # Scale factor from pixel coordinates (at DPI) back to 72dpi PDF points
                    scale_x = page.rect.width / max(pix.w, 1)
                    scale_y = page.rect.height / max(pix.h, 1)

                    lines = ocr_results[0] if (ocr_results and len(ocr_results) > 0 and ocr_results[0]) else []

                    for line in lines:
                        pts, (text, conf) = line
                        if not text or not text.strip():
                            continue
                        if conf < self.confidence_threshold:
                            continue

                        # Compute bounding box in PDF points
                        x0 = min(pt[0] for pt in pts) * scale_x
                        y0 = min(pt[1] for pt in pts) * scale_y
                        x1 = max(pt[0] for pt in pts) * scale_x
                        y1 = max(pt[1] for pt in pts) * scale_y
                        b_rect = fitz.Rect(x0, y0, x1, y1)

                        # Skip text that falls within an extracted table or figure on THIS page
                        if page_occupied and any(
                            b_rect.intersects(fitz.Rect(*ob))
                            and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                            for ob in page_occupied
                        ):
                            continue

                        cleaned_text = text.strip()
                        classification = BlockType.TEXT
                        level: int | None = None

                        if len(cleaned_text.splitlines()) <= 2 and len(cleaned_text) < 80:
                            if cleaned_text.isupper() or cleaned_text.startswith("#"):
                                classification = BlockType.HEADING
                                level = 1 if cleaned_text.isupper() else 2

                        block_id = f"{doc_id}_p{p_num}_b{order}"
                        page_blocks.append(
                            Block(
                                id=block_id,
                                doc_id=doc_id,
                                page=p_num,
                                bbox=(round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)),
                                type=classification,
                                text=cleaned_text,
                                level=level,
                                order=order,
                                meta={
                                    "source": "paddleocr",
                                    "confidence": round(float(conf), 4),
                                    "lang": self.lang,
                                },
                            )
                        )
                        order += 1

                except Exception as e:
                    logger.warning(
                        f"PaddleOCR processing error on page {p_num} of '{path.name}': {e}. Falling back to native extraction."
                    )
                    page_blocks = []

            # Fallback if PaddleOCR produced 0 blocks on this page or is unavailable
            if not page_blocks:
                try:
                    # Attempt PyMuPDF native OCR
                    textpage = page.get_textpage_ocr(language="eng", dpi=self.dpi)
                    for b in textpage.extractBLOCKS():
                        x0, y0, x1, y1, text, _, b_type = b
                        if b_type == 0 and text.strip():
                            b_rect = fitz.Rect(x0, y0, x1, y1)
                            if page_occupied and any(
                                b_rect.intersects(fitz.Rect(*ob))
                                and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                                for ob in page_occupied
                            ):
                                continue

                            page_blocks.append(
                                Block(
                                    id=f"{doc_id}_p{p_num}_b{order}",
                                    doc_id=doc_id,
                                    page=p_num,
                                    bbox=(round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)),
                                    type=BlockType.TEXT,
                                    text=text.strip(),
                                    order=order,
                                    meta={"source": "paddleocr_fallback_ocr"},
                                )
                            )
                            order += 1
                except Exception:
                    # Final fallback: PyMuPDF standard digital text
                    for b in page.get_text("blocks"):
                        x0, y0, x1, y1, text, _, b_type = b
                        if b_type == 0 and text.strip():
                            b_rect = fitz.Rect(x0, y0, x1, y1)
                            if page_occupied and any(
                                b_rect.intersects(fitz.Rect(*ob))
                                and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                                for ob in page_occupied
                            ):
                                continue

                            page_blocks.append(
                                Block(
                                    id=f"{doc_id}_p{p_num}_b{order}",
                                    doc_id=doc_id,
                                    page=p_num,
                                    bbox=(round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)),
                                    type=BlockType.TEXT,
                                    text=text.strip(),
                                    order=order,
                                    meta={"source": "paddleocr_fallback_digital"},
                                )
                            )
                            order += 1

            blocks.extend(page_blocks)

        doc.close()

        # 3. Append multimodal figure and table blocks
        blocks.extend(mm_blocks)
        blocks.sort(key=lambda b: (b.page, b.order))

        logger.info(f"PaddleOCRParser: extracted {len(blocks)} blocks from '{path.name}'")
        return blocks
