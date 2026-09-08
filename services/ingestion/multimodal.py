"""Multimodal extraction engine for deep table and figure extraction from PDFs."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from contracts.document import Block, BlockType
from services.common.logger import get_logger

logger = get_logger("ingestion.multimodal")

FIGURES_DIR = Path("data/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)


class MultimodalExtractor:
    """Extracts tables as clean Markdown and figures as rendered PNGs with captions."""

    def __init__(self, figures_dir: Path | str = FIGURES_DIR) -> None:
        self.figures_dir = Path(figures_dir)
        self.figures_dir.mkdir(parents=True, exist_ok=True)

    def extract_tables_and_figures(
        self,
        doc: fitz.Document,
        doc_id: str,
    ) -> tuple[list[Block], list[tuple[float, float, float, float]]]:
        """Extracts all tables and figures across document pages.

        Returns:
            blocks: List of table and figure Blocks with metadata.
            occupied_bboxes: List of bounding boxes occupied by tables and figures to avoid duplication with text blocks.
        """
        multimodal_blocks: list[Block] = []
        occupied_bboxes: list[tuple[float, float, float, float]] = []

        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            order = 0

            # 1. Deep Table Extraction
            table_blocks, t_bboxes = self._extract_tables_for_page(page, p_num, doc_id, order)
            multimodal_blocks.extend(table_blocks)
            occupied_bboxes.extend(t_bboxes)
            order += len(table_blocks)

            # 2. Deep Figure & Diagram Extraction
            fig_blocks, f_bboxes = self._extract_figures_for_page(page, p_num, doc_id, order)
            multimodal_blocks.extend(fig_blocks)
            occupied_bboxes.extend(f_bboxes)

        logger.info(
            f"MultimodalExtractor: extracted {len(multimodal_blocks)} multimodal blocks "
            f"({sum(1 for b in multimodal_blocks if b.type == BlockType.TABLE)} tables, "
            f"{sum(1 for b in multimodal_blocks if b.type == BlockType.IMAGE)} figures) for doc '{doc_id}'"
        )
        return multimodal_blocks, occupied_bboxes

    def _extract_tables_for_page(
        self,
        page: fitz.Page,
        p_num: int,
        doc_id: str,
        start_order: int,
    ) -> tuple[list[Block], list[tuple[float, float, float, float]]]:
        blocks: list[Block] = []
        bboxes: list[tuple[float, float, float, float]] = []

        try:
            tab_finder = page.find_tables()
            tables = list(tab_finder)
            for idx, tab in enumerate(tables):
                tab_bbox = tuple(tab.bbox)
                md_text = tab.to_markdown().strip()
                if not md_text:
                    continue

                # Search for contextual table caption directly above table
                caption = self._find_nearby_caption(page, tab.bbox, is_above=True, prefix_pattern=r"(?i)table\s+\d+")

                # Extract headers and data
                headers = [str(h) for h in (tab.header.names if tab.header else [])]
                row_count = getattr(tab, "row_count", 0)
                col_count = getattr(tab, "col_count", len(headers))

                # If caption found, prefix the markdown table with heading
                formatted_text = md_text
                if caption:
                    formatted_text = f"### {caption}\n\n{md_text}"

                block_id = f"{doc_id}_p{p_num}_table_{idx}"
                block = Block(
                    id=block_id,
                    doc_id=doc_id,
                    page=p_num,
                    bbox=tab_bbox,
                    type=BlockType.TABLE,
                    text=formatted_text,
                    html=getattr(tab, "to_html", lambda: None)(),
                    caption=caption,
                    order=start_order + idx,
                    meta={
                        "headers": headers,
                        "row_count": row_count,
                        "col_count": col_count,
                        "is_multimodal_table": True,
                    },
                )
                blocks.append(block)
                bboxes.append(tab_bbox)
        except Exception as e:
            logger.warning(f"Error extracting tables on page {p_num}: {e}")

        return blocks, bboxes

    def _extract_figures_for_page(
        self,
        page: fitz.Page,
        p_num: int,
        doc_id: str,
        start_order: int,
    ) -> tuple[list[Block], list[tuple[float, float, float, float]]]:
        blocks: list[Block] = []
        bboxes: list[tuple[float, float, float, float]] = []

        try:
            images = page.get_images(full=True)
            seen_rects: set[tuple[int, int, int, int]] = set()
            fig_idx = 0

            for img_info in images:
                xref = img_info[0]
                rects = page.get_image_rects(xref)
                if not rects:
                    continue

                for r in rects:
                    # Ignore tiny decorative icons, bullet dots, divider lines
                    if r.width < 60 or r.height < 50:
                        continue

                    rect_key = (int(r.x0), int(r.y0), int(r.x1), int(r.y1))
                    if rect_key in seen_rects:
                        continue
                    seen_rects.add(rect_key)

                    # Look for caption below or above image
                    caption = self._find_nearby_caption(
                        page,
                        (r.x0, r.y0, r.x1, r.y1),
                        is_above=False,
                        prefix_pattern=r"(?i)(figure|fig\.|diagram|architecture|flowchart)\s*\d*",
                    )
                    if not caption:
                        caption = f"Figure on Page {p_num}"

                    # Render figure crop to PNG
                    fig_filename = f"{doc_id}_p{p_num}_fig_{fig_idx}.png"
                    fig_path = self.figures_dir / fig_filename
                    try:
                        # Add a small 4pt padding around crop
                        clip_rect = fitz.Rect(
                            max(0.0, r.x0 - 4),
                            max(0.0, r.y0 - 4),
                            min(page.rect.width, r.x1 + 4),
                            min(page.rect.height, r.y1 + 4),
                        )
                        pix = page.get_pixmap(clip=clip_rect, dpi=150)
                        pix.save(str(fig_path))
                    except Exception as e:
                        logger.warning(f"Could not render figure crop {fig_filename}: {e}")

                    rel_path = f"data/figures/{fig_filename}"
                    fig_text = (
                        f"### {caption}\n\n"
                        f"![{caption}](/{rel_path})\n\n"
                        f"Visual illustration/diagram showing: {caption} on page {p_num}."
                    )

                    fig_bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                    block_id = f"{doc_id}_p{p_num}_fig_{fig_idx}"
                    block = Block(
                        id=block_id,
                        doc_id=doc_id,
                        page=p_num,
                        bbox=fig_bbox,
                        type=BlockType.IMAGE,
                        text=fig_text,
                        image_path=rel_path,
                        caption=caption,
                        order=start_order + fig_idx,
                        meta={
                            "width": round(r.width, 1),
                            "height": round(r.height, 1),
                            "image_filename": fig_filename,
                            "is_multimodal_figure": True,
                        },
                    )
                    blocks.append(block)
                    bboxes.append(fig_bbox)
                    fig_idx += 1

        except Exception as e:
            logger.warning(f"Error extracting figures on page {p_num}: {e}")

        return blocks, bboxes

    def _find_nearby_caption(
        self,
        page: fitz.Page,
        bbox: tuple[float, float, float, float],
        is_above: bool,
        prefix_pattern: str,
        search_distance: float = 45.0,
    ) -> str | None:
        """Finds caption text near a table or figure bounding box."""
        bx0, by0, bx1, by1 = bbox
        blocks = page.get_text("blocks")
        candidate_captions: list[str] = []

        for b in blocks:
            x0, y0, x1, y1, text, _, b_type = b
            if b_type != 0 or not text.strip():
                continue

            cleaned_text = " ".join(text.split())
            if is_above:
                # Text should be right above the box
                if y1 <= by0 + 5 and y1 >= by0 - search_distance:
                    if re.search(prefix_pattern, cleaned_text):
                        candidate_captions.append(cleaned_text)
            else:
                # Text should be right below the box
                if y0 >= by1 - 5 and y0 <= by1 + search_distance:
                    if re.search(prefix_pattern, cleaned_text):
                        candidate_captions.append(cleaned_text)

        if candidate_captions:
            # Pick shortest or closest match
            return candidate_captions[0]
        return None
