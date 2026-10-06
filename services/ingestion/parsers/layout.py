"""Layout-aware multimodal parser for tables, figures, and multi-column documents.

Powered by IBM Docling for deep document layout analysis, semantic hierarchy
extraction (titles, section headers, subheadings, tables, and code), and bounding box
provenance. Falls back to font-size-aware PyMuPDF text & table extraction if Docling
is unavailable or raises an unexpected conversion error (IRA-61, IRA-63).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from contracts.document import Block, BlockType
from services.common.logger import get_logger
from services.ingestion.multimodal import MultimodalExtractor

logger = get_logger("ingestion.layout")

try:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import DocItemLabel
    _HAS_DOCLING = True
except ImportError:
    _HAS_DOCLING = False


class LayoutParser:
    """Extracts tables, figures, and text with semantic hierarchy and bounding box provenance."""

    def __init__(self) -> None:
        self.multimodal_extractor = MultimodalExtractor()
        self._docling_converter: Any = None

    def _get_docling_converter(self) -> Any:
        if not _HAS_DOCLING:
            return None
        if self._docling_converter is None:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False  # Keep fast CPU inference for digital PDFs; probe routes scans to 'ocr'
            pipeline_options.do_table_structure = True
            self._docling_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        return self._docling_converter

    def parse(self, file_path: str, doc_id: str) -> list[Block]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not _HAS_DOCLING:
            logger.warning(
                f"Docling is not installed; parsing '{path.name}' with the PyMuPDF fallback "
                "(install the 'parse' extra to enable it)."
            )
        if _HAS_DOCLING:
            try:
                converter = self._get_docling_converter()
                if converter is not None:
                    blocks = self._parse_with_docling(converter, path, doc_id)
                    if blocks:
                        return blocks
            except Exception as exc:
                logger.warning(
                    f"Docling layout parsing failed for '{path.name}': {exc}. "
                    "Falling back to enhanced PyMuPDF layout parsing."
                )

        return self._parse_fallback(path, doc_id)

    def _parse_with_docling(self, converter: Any, path: Path, doc_id: str) -> list[Block]:
        """Parses document using Docling AST (titles, section headers, tables, code)."""
        conv_res = converter.convert(str(path))
        doc = conv_res.document

        blocks: list[Block] = []
        order = 0

        # Build mapping of page number to height for coordinate normalization
        page_heights: dict[int, float] = {}
        if hasattr(doc, "pages"):
            for p_no, p_data in doc.pages.items():
                if hasattr(p_data, "size") and hasattr(p_data.size, "height"):
                    page_heights[p_no] = float(p_data.size.height)

        for item, level in doc.iterate_items():
            label = getattr(item, "label", None)
            if label is None:
                continue

            # Skip header/footer chrome
            if label in (
                DocItemLabel.PAGE_HEADER,
                DocItemLabel.PAGE_FOOTER,
                DocItemLabel.DOCUMENT_INDEX,
            ):
                continue

            # Determine primary page and bounding box
            page_no = 1
            bbox = (0.0, 0.0, 0.0, 0.0)
            prov_list = getattr(item, "prov", [])
            if prov_list:
                first_prov = prov_list[0]
                page_no = getattr(first_prov, "page_no", 1)
                item_bbox = getattr(first_prov, "bbox", None)
                if item_bbox is not None:
                    p_height = page_heights.get(page_no, 792.0)
                    try:
                        tl_bbox = item_bbox.to_top_left_origin(p_height)
                        bbox = (
                            round(float(tl_bbox.l), 2),
                            round(float(tl_bbox.t), 2),
                            round(float(tl_bbox.r), 2),
                            round(float(tl_bbox.b), 2),
                        )
                    except Exception:
                        bbox = (
                            round(float(getattr(item_bbox, "l", 0.0)), 2),
                            round(float(getattr(item_bbox, "t", 0.0)), 2),
                            round(float(getattr(item_bbox, "r", 0.0)), 2),
                            round(float(getattr(item_bbox, "b", 0.0)), 2),
                        )

            # Classify block type and extract semantic attributes
            b_type = BlockType.TEXT
            b_level: int | None = None
            text = ""
            html: str | None = None
            caption: str | None = None

            if label == DocItemLabel.TITLE:
                b_type = BlockType.HEADING
                b_level = 1
                text = getattr(item, "text", "").strip()

            elif label == DocItemLabel.SECTION_HEADER:
                b_type = BlockType.HEADING
                b_level = getattr(item, "level", None) or level or 2
                text = getattr(item, "text", "").strip()

            elif label == DocItemLabel.TABLE:
                b_type = BlockType.TABLE
                if hasattr(item, "export_to_markdown"):
                    text = item.export_to_markdown().strip()
                elif hasattr(item, "text"):
                    text = item.text.strip()
                if hasattr(item, "export_to_html"):
                    html = item.export_to_html()

            elif label in (DocItemLabel.PICTURE, DocItemLabel.CHART):
                b_type = BlockType.IMAGE
                caption = getattr(item, "caption", None)
                text = getattr(item, "text", "").strip()
                if not text:
                    # Docling sometimes tags real text (e.g. a large title) as a picture; recover
                    # it from the PDF's own text layer rather than emit a "Figure" placeholder.
                    layer_text = self._text_in_bbox(path, page_no, bbox)
                    if layer_text:
                        text = layer_text
                        if len(text) < 80 and len(text.splitlines()) == 1:
                            b_type, b_level = BlockType.HEADING, 2
                        else:
                            b_type = BlockType.TEXT
                    else:
                        text = f"Figure on page {page_no}"

            elif label == DocItemLabel.CODE:
                b_type = BlockType.CODE
                text = getattr(item, "text", "").strip()

            elif label in (DocItemLabel.CAPTION,):
                b_type = BlockType.CAPTION
                text = getattr(item, "text", "").strip()

            else:
                text = getattr(item, "text", "").strip()
                # Enhanced semantic refinement: if Docling emitted text, but it's a section title/header
                if (
                    len(text.splitlines()) <= 2
                    and len(text) < 80
                    and not text.endswith((".", ";", ","))
                    and (
                        text.startswith("#")
                        or text.isupper()
                        or (len(text.split()) <= 8 and (text.istitle() or not any(c.islower() for c in text[:1])))
                    )
                ):
                    b_type = BlockType.HEADING
                    b_level = 2
                    if text.startswith("#"):
                        hashes = len(text) - len(text.lstrip("#"))
                        b_level = min(max(hashes, 1), 6)
                        text = text.lstrip("#").strip()
                else:
                    b_type = BlockType.TEXT

            if not text:
                continue

            block_id = f"{doc_id}_p{page_no}_b{order}"
            blocks.append(
                Block(
                    id=block_id,
                    doc_id=doc_id,
                    page=page_no,
                    bbox=bbox,
                    type=b_type,
                    text=text,
                    html=html,
                    caption=caption,
                    level=b_level,
                    order=order,
                    meta={"label": str(label.value if hasattr(label, "value") else label)},
                )
            )
            order += 1

        # Sort blocks chronologically by page then vertical position
        blocks.sort(key=lambda b: (b.page, b.bbox[1]))
        logger.info(
            f"DoclingParser: extracted {len(blocks)} structured blocks from '{path.name}' "
            f"across {len(doc.pages) if hasattr(doc, 'pages') else '?'} pages"
        )
        return blocks

    @staticmethod
    def _text_in_bbox(path: Path, page_no: int, bbox: tuple[float, float, float, float]) -> str:
        """Text-layer content inside a top-left-origin bbox, or '' (scans, empty or bad regions)."""
        try:
            with fitz.open(str(path)) as pdf:
                rect = fitz.Rect(*bbox)
                if rect.is_empty or not 1 <= page_no <= len(pdf):
                    return ""
                return pdf[page_no - 1].get_text("text", clip=rect).strip()
        except Exception:
            return ""

    def _parse_fallback(self, path: Path, doc_id: str) -> list[Block]:
        """Enhanced PyMuPDF fallback with font-size heading detection, tables, and figures."""
        doc = fitz.open(str(path))
        blocks: list[Block] = []

        # 1. Extract Multimodal Elements (Tables & Figures)
        mm_blocks, occupied_bboxes = self.multimodal_extractor.extract_tables_and_figures(doc, doc_id)
        blocks.extend(mm_blocks)

        # 2. Extract Text and Headings via Dict (inspecting font size and bold weights)
        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            order = 1000 + p_idx * 100
            page_occupied = (
                occupied_bboxes.get(p_num, [])
                if isinstance(occupied_bboxes, dict)
                else occupied_bboxes
            )

            page_dict = page.get_text("dict")
            for b in page_dict.get("blocks", []):
                b_type = b.get("type", 0)
                bbox = tuple(b.get("bbox", (0.0, 0.0, 0.0, 0.0)))
                b_rect = fitz.Rect(*bbox)

                # Skip if block is inside or significantly overlaps an extracted table/figure
                if page_occupied and any(
                    b_rect.intersects(fitz.Rect(*ob))
                    and (b_rect & fitz.Rect(*ob)).get_area() > 0.4 * b_rect.get_area()
                    for ob in page_occupied
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
                            span_text = span.get("text", "")
                            if span_text:
                                line_text_parts.append(span_text)
                                size = span.get("size", 10.0)
                                if size > max_size:
                                    max_size = size
                                flags = span.get("flags", 0)
                                font_name = span.get("font", "").lower()
                                if (flags & 2) or ("bold" in font_name) or ("black" in font_name) or ("heavy" in font_name):
                                    is_bold = True
                        if line_text_parts:
                            block_text_parts.append(" ".join(line_text_parts))

                    cleaned_text = "\n".join(block_text_parts).strip()
                    if not cleaned_text:
                        continue

                    # Multi-signal heading classification:
                    # 1. Font size and bold weight
                    # 2. Markdown '#' prefix
                    # 3. Short standalone all-caps lines
                    classification = BlockType.TEXT
                    level: int | None = None

                    if cleaned_text.startswith("#"):
                        classification = BlockType.HEADING
                        hashes = len(cleaned_text) - len(cleaned_text.lstrip("#"))
                        level = min(max(hashes, 1), 6)
                        cleaned_text = cleaned_text.lstrip("#").strip()
                    elif max_size >= 16.0 or (max_size >= 14.0 and is_bold):
                        classification = BlockType.HEADING
                        level = 1 if max_size >= 18.0 else 2
                    elif max_size >= 12.0 and is_bold:
                        classification = BlockType.HEADING
                        level = 3
                    elif (
                        len(cleaned_text.splitlines()) <= 2
                        and len(cleaned_text) < 80
                        and cleaned_text.isupper()
                    ):
                        classification = BlockType.HEADING
                        level = 1

                    block_id = f"{doc_id}_p{p_num}_txt_{order}"
                    blocks.append(
                        Block(
                            id=block_id,
                            doc_id=doc_id,
                            page=p_num,
                            bbox=(
                                round(float(bbox[0]), 2),
                                round(float(bbox[1]), 2),
                                round(float(bbox[2]), 2),
                                round(float(bbox[3]), 2),
                            ),
                            type=classification,
                            text=cleaned_text,
                            level=level,
                            order=order,
                            meta={"font_size": max_size, "is_bold": is_bold},
                        )
                    )
                    order += 1

        doc.close()
        blocks.sort(key=lambda b: (b.page, b.bbox[1]))
        logger.info(
            f"LayoutParser fallback: extracted {len(blocks)} total blocks "
            f"({len(mm_blocks)} multimodal, {len(blocks) - len(mm_blocks)} text) from '{path.name}'"
        )
        return blocks
