"""Content-aware chunker with table windowing, heading hierarchy, and 512-token cap."""

from __future__ import annotations

import re
from typing import Any

from contracts.chunk import Chunk
from contracts.document import Block, BlockType
from services.common.logger import get_logger

logger = get_logger("indexing.chunker")


def estimate_tokens(text: str) -> int:
    """Fast approximation of token count (~4 characters or ~0.75 words per token)."""
    words = len(text.split())
    chars = len(text)
    # Conservative estimate
    return max(int(words * 1.3), int(chars / 3.8), 1)


def split_large_table(table_text: str, max_tokens: int = 512) -> list[str]:
    """Splits an oversized markdown table while repeating table headers on every chunk."""
    lines = [line for line in table_text.strip().split("\n") if line.strip()]
    if len(lines) <= 2:
        return [table_text]

    header = lines[0]
    separator = lines[1] if len(lines) > 1 and "---" in lines[1] else "| " + " | ".join(["---"] * len(header.split("|")[1:-1])) + " |"
    data_rows = lines[2:] if len(lines) > 2 and "---" in lines[1] else lines[1:]

    chunks: list[str] = []
    current_rows: list[str] = []
    base_tokens = estimate_tokens(f"{header}\n{separator}\n")

    for row in data_rows:
        row_tokens = estimate_tokens(row + "\n")
        current_tokens = sum(estimate_tokens(r + "\n") for r in current_rows)

        if base_tokens + current_tokens + row_tokens > max_tokens and current_rows:
            chunk_content = f"{header}\n{separator}\n" + "\n".join(current_rows)
            chunks.append(chunk_content)
            current_rows = [row]
        else:
            current_rows.append(row)

    if current_rows:
        chunks.append(f"{header}\n{separator}\n" + "\n".join(current_rows))

    return chunks or [table_text]


def split_text_recursive(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Recursively splits text on paragraph breaks, line breaks, and sentences."""
    if estimate_tokens(text) <= max_tokens:
        return [text]

    splits: list[str] = []
    paragraphs = text.split("\n\n")

    current_para: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p_tokens = estimate_tokens(p)
        current_tokens = sum(estimate_tokens(x) for x in current_para)

        if current_tokens + p_tokens > max_tokens:
            if current_para:
                splits.append("\n\n".join(current_para))
                current_para = []

            # If a single paragraph exceeds max_tokens, split on sentences
            if p_tokens > max_tokens:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                curr_sent: list[str] = []
                for s in sentences:
                    s_tok = estimate_tokens(s)
                    if sum(estimate_tokens(x) for x in curr_sent) + s_tok > max_tokens and curr_sent:
                        splits.append(" ".join(curr_sent))
                        curr_sent = [s]
                    else:
                        curr_sent.append(s)
                if curr_sent:
                    splits.append(" ".join(curr_sent))
            else:
                current_para.append(p)
        else:
            current_para.append(p)

    if current_para:
        splits.append("\n\n".join(current_para))

    return splits or [text[: max_tokens * 4]]


def chunk_blocks(
    blocks: list[Block],
    doc_id: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Processes extracted blocks into hierarchical, token-capped chunks with contiguous block packing."""
    chunks: list[Chunk] = []
    heading_stack: list[str] = []
    chunk_index = 0

    accum_texts: list[str] = []
    accum_bboxes: list[tuple[float, float, float, float]] = []
    accum_page: int | None = None
    accum_meta: dict[str, Any] = {}

    def flush_accumulated_text() -> None:
        nonlocal chunk_index, accum_texts, accum_bboxes, accum_page, accum_meta
        if not accum_texts or accum_page is None:
            accum_texts.clear()
            accum_bboxes.clear()
            accum_page = None
            accum_meta.clear()
            return

        combined_text = "\n\n".join(accum_texts).strip()
        if not combined_text:
            accum_texts.clear()
            accum_bboxes.clear()
            accum_page = None
            accum_meta.clear()
            return

        union_bbox = (
            min(b[0] for b in accum_bboxes),
            min(b[1] for b in accum_bboxes),
            max(b[2] for b in accum_bboxes),
            max(b[3] for b in accum_bboxes),
        )
        breadcrumb = " > ".join(heading_stack)
        text_splits = split_text_recursive(combined_text, max_tokens=max_tokens - 40, overlap=overlap_tokens)

        for split in text_splits:
            enriched_text = f"Section: {breadcrumb}\n\n{split}" if breadcrumb and not split.startswith("Section:") else split
            tok_count = min(estimate_tokens(enriched_text), 512)

            chunks.append(
                Chunk(
                    id=f"{doc_id}_c{chunk_index}",
                    doc_id=doc_id,
                    page=accum_page,
                    page_end=accum_page,
                    bbox=union_bbox,
                    text=enriched_text,
                    raw_text=split,
                    token_count=tok_count,
                    headings=list(heading_stack),
                    is_table=False,
                    meta=dict(accum_meta),
                )
            )
            chunk_index += 1

        accum_texts.clear()
        accum_bboxes.clear()
        accum_page = None
        accum_meta.clear()

    for block in blocks:
        # Update heading hierarchy stack
        if block.type == BlockType.HEADING:
            flush_accumulated_text()
            level = block.level or 1
            # Pop headings of same or deeper level
            heading_stack = heading_stack[: max(level - 1, 0)]
            heading_stack.append(block.text.strip())

        # Handle Tables
        elif block.type == BlockType.TABLE:
            flush_accumulated_text()
            table_chunks = split_large_table(block.text, max_tokens=max_tokens)
            for t_text in table_chunks:
                breadcrumb = " > ".join(heading_stack)
                enriched_text = f"Table ({breadcrumb}):\n{t_text}" if breadcrumb else t_text
                tok_count = min(estimate_tokens(enriched_text), 512)

                chunks.append(
                    Chunk(
                        id=f"{doc_id}_c{chunk_index}",
                        doc_id=doc_id,
                        page=block.page,
                        page_end=block.page,
                        bbox=block.bbox,
                        text=enriched_text,
                        raw_text=t_text,
                        token_count=tok_count,
                        headings=list(heading_stack),
                        is_table=True,
                        is_figure=False,
                        caption=block.caption,
                        table_markdown=t_text,
                        meta=block.meta,
                    )
                )
                chunk_index += 1

        # Handle Figures & Diagrams
        elif block.type == BlockType.IMAGE:
            flush_accumulated_text()
            breadcrumb = " > ".join(heading_stack)
            raw_text = block.text.strip()
            enriched_text = f"Figure ({breadcrumb}):\n{raw_text}" if breadcrumb else raw_text
            tok_count = min(estimate_tokens(enriched_text), 512)

            chunks.append(
                Chunk(
                    id=f"{doc_id}_c{chunk_index}",
                    doc_id=doc_id,
                    page=block.page,
                    page_end=block.page,
                    bbox=block.bbox,
                    text=enriched_text,
                    raw_text=raw_text,
                    token_count=tok_count,
                    headings=list(heading_stack),
                    is_table=False,
                    is_figure=True,
                    image_path=block.image_path,
                    caption=block.caption,
                    meta=block.meta,
                )
            )
            chunk_index += 1

        # Handle Regular Text
        else:
            raw_text = block.text.strip()
            if not raw_text:
                continue

            block_tok = estimate_tokens(raw_text)
            curr_tok = sum(estimate_tokens(t) for t in accum_texts)

            # Flush if page boundary crossed or max_tokens reached
            if accum_page is not None and (accum_page != block.page or curr_tok + block_tok > (max_tokens - 40)):
                flush_accumulated_text()

            accum_texts.append(raw_text)
            accum_bboxes.append(block.bbox)
            accum_page = block.page
            if not accum_meta and block.meta:
                accum_meta = dict(block.meta)

    # Flush remaining text
    flush_accumulated_text()

    logger.info(f"Chunker: generated {len(chunks)} chunks for doc_id='{doc_id}' (max_tokens={max_tokens})")
    return chunks
