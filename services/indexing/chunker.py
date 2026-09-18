"""Content-aware chunker with table windowing, heading hierarchy, sliding window overlap, and 512-token cap (REC-59)."""

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


def format_breadcrumb(headings: list[str], max_tokens_budget: int = 36) -> str:
    """Formats heading stack into breadcrumb hierarchy, budgeted within max token limit."""
    if not headings:
        return ""
    full = " > ".join(headings)
    if estimate_tokens(full) <= max_tokens_budget:
        return full
    if len(headings) > 2:
        shortened = f"{headings[0]} > ... > {headings[-1]}"
        if estimate_tokens(shortened) <= max_tokens_budget:
            return shortened
    return headings[-1][: max_tokens_budget * 3]


def extract_overlap_prefix(text: str, overlap_tokens: int) -> str:
    """Extracts an overlap snippet from the end of a chunk for semantic continuity in the next chunk."""
    if overlap_tokens <= 0 or not text.strip():
        return ""

    # Prefer sentence-level boundaries if possible
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(sentences) > 1:
        accum_sentences: list[str] = []
        accum_tok = 0
        for s in reversed(sentences):
            tok = estimate_tokens(s)
            if accum_sentences and (accum_tok + tok > overlap_tokens):
                break
            accum_sentences.append(s)
            accum_tok += tok
            if accum_tok >= overlap_tokens:
                break
        if accum_sentences:
            candidate = " ".join(reversed(accum_sentences))
            if estimate_tokens(candidate) <= int(overlap_tokens * 1.3):
                return candidate

    # Fallback to word-level boundaries
    words = text.strip().split()
    accum_words: list[str] = []
    for w in reversed(words):
        accum_words.append(w)
        if estimate_tokens(" ".join(accum_words)) >= overlap_tokens:
            break
    return " ".join(reversed(accum_words))


def _split_to_fit(text: str, target_max: int, level: int = 0) -> list[str]:
    """Recursively breaks down text along delimiter hierarchy until each unit <= target_max."""
    text = text.strip()
    if not text:
        return []
    if estimate_tokens(text) <= target_max:
        return [text]

    delimiters = [
        ("\n\n", True),            # Paragraphs
        ("\n", True),              # Lines
        (r"(?<=[.!?])\s+", False), # Sentences
        (r"(?<=[;:,])\s+", False), # Clauses / phrases
        (r"\s+", False),           # Words
    ]

    if level >= len(delimiters):
        char_limit = max(int(target_max * 3.5), 20)
        return [
            text[i : i + char_limit].strip()
            for i in range(0, len(text), char_limit)
            if text[i : i + char_limit].strip()
        ]

    delim, is_literal = delimiters[level]
    if is_literal:
        parts = text.split(delim)
    else:
        parts = re.split(delim, text)

    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return _split_to_fit(text, target_max, level + 1)

    result: list[str] = []
    for part in parts:
        if estimate_tokens(part) <= target_max:
            result.append(part)
        else:
            result.extend(_split_to_fit(part, target_max, level + 1))
    return result


def split_text_recursive(text: str, max_tokens: int = 512, overlap: int = 64) -> list[str]:
    """Recursively splits text on paragraph breaks, line breaks, and sentences with true token overlap."""
    text = text.strip()
    if not text:
        return []
    if estimate_tokens(text) <= max_tokens:
        return [text]

    effective_overlap = min(max(overlap, 0), max_tokens // 4)
    target_unit_max = max(max_tokens - effective_overlap, max_tokens // 2)

    units = _split_to_fit(text, target_unit_max)
    if not units:
        return []

    chunks: list[str] = []
    current_chunk: list[str] = []

    def join_units(units_list: list[str]) -> str:
        if not units_list:
            return ""
        res = units_list[0]
        for u in units_list[1:]:
            if "\n" in res or "\n" in u:
                res = f"{res}\n\n{u}"
            else:
                res = f"{res} {u}"
        return res

    for unit in units:
        test_units = current_chunk + [unit]
        test_text = join_units(test_units)
        if current_chunk and estimate_tokens(test_text) > max_tokens:
            chunk_str = join_units(current_chunk)
            chunks.append(chunk_str)
            overlap_prefix = extract_overlap_prefix(chunk_str, effective_overlap)
            if overlap_prefix:
                current_chunk = [overlap_prefix, unit]
            else:
                current_chunk = [unit]
        else:
            current_chunk.append(unit)

    if current_chunk:
        chunks.append(join_units(current_chunk))

    return chunks or [text[: max_tokens * 3]]


def split_large_table(table_text: str, max_tokens: int = 512, overlap_rows: int = 1) -> list[str]:
    """Splits an oversized markdown table while repeating table headers and preserving row continuity."""
    lines = [line for line in table_text.strip().split("\n") if line.strip()]
    if len(lines) <= 2:
        return [table_text]

    header = lines[0]
    separator = (
        lines[1]
        if len(lines) > 1 and "---" in lines[1]
        else "| " + " | ".join(["---"] * len(header.split("|")[1:-1])) + " |"
    )
    data_rows = lines[2:] if len(lines) > 2 and "---" in lines[1] else lines[1:]

    chunks: list[str] = []
    current_rows: list[str] = []
    base_header = f"{header}\n{separator}\n"
    base_tokens = estimate_tokens(base_header)

    if base_tokens >= max_tokens:
        return [table_text[: max_tokens * 3]]

    for row in data_rows:
        row_tokens = estimate_tokens(row + "\n")
        if base_tokens + row_tokens > max_tokens:
            row = row[: max((max_tokens - base_tokens) * 3, 20)] + " ... |"
            row_tokens = estimate_tokens(row + "\n")

        current_tokens = sum(estimate_tokens(r + "\n") for r in current_rows)

        if base_tokens + current_tokens + row_tokens > max_tokens and current_rows:
            chunk_content = f"{base_header}" + "\n".join(current_rows)
            chunks.append(chunk_content)
            if overlap_rows > 0 and len(current_rows) >= 1:
                last_row = current_rows[-1]
                if base_tokens + estimate_tokens(last_row + "\n") + row_tokens <= max_tokens:
                    current_rows = [last_row, row]
                else:
                    current_rows = [row]
            else:
                current_rows = [row]
        else:
            current_rows.append(row)

    if current_rows:
        chunks.append(f"{base_header}" + "\n".join(current_rows))

    return chunks or [table_text]


def _match_bboxes_for_split(
    split_text: str,
    block_entries: list[tuple[str, tuple[float, float, float, float]]],
) -> tuple[float, float, float, float]:
    """Computes bounding box covering only the blocks present in the given text split."""
    if not block_entries:
        return (0.0, 0.0, 0.0, 0.0)

    matched: list[tuple[float, float, float, float]] = []
    for b_text, bbox in block_entries:
        words = b_text.split()
        if len(words) <= 3:
            if b_text in split_text:
                matched.append(bbox)
        else:
            prefix_sample = " ".join(words[:4])
            suffix_sample = " ".join(words[-4:])
            mid_idx = len(words) // 2
            mid_sample = " ".join(words[mid_idx : mid_idx + 4])
            if prefix_sample in split_text or suffix_sample in split_text or mid_sample in split_text:
                matched.append(bbox)

    target_bboxes = matched or [b for _, b in block_entries]
    return (
        min(b[0] for b in target_bboxes),
        min(b[1] for b in target_bboxes),
        max(b[2] for b in target_bboxes),
        max(b[3] for b in target_bboxes),
    )


def chunk_blocks(
    blocks: list[Block],
    doc_id: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Processes extracted blocks into hierarchical, token-capped chunks with contiguous block packing (REC-59)."""
    chunks: list[Chunk] = []
    heading_stack: list[str] = []
    chunk_index = 0

    accum_blocks: list[tuple[str, tuple[float, float, float, float]]] = []
    accum_page: int | None = None
    accum_meta: dict[str, Any] = {}

    def flush_accumulated_text() -> None:
        nonlocal chunk_index, accum_blocks, accum_page, accum_meta
        if not accum_blocks or accum_page is None:
            accum_blocks.clear()
            accum_page = None
            accum_meta.clear()
            return

        combined_text = "\n\n".join(t for t, _ in accum_blocks).strip()
        if not combined_text:
            accum_blocks.clear()
            accum_page = None
            accum_meta.clear()
            return

        breadcrumb = format_breadcrumb(heading_stack, max_tokens_budget=36)
        prefix = f"Section: {breadcrumb}\n\n" if breadcrumb else ""
        prefix_tokens = estimate_tokens(prefix) if prefix else 0
        text_budget = max(max_tokens - prefix_tokens - 8, max_tokens // 2)

        text_splits = split_text_recursive(combined_text, max_tokens=text_budget, overlap=overlap_tokens)

        for split in text_splits:
            split_bbox = _match_bboxes_for_split(split, accum_blocks)
            enriched_text = f"{prefix}{split}" if prefix and not split.startswith("Section:") else split
            tok_count = min(max(estimate_tokens(enriched_text), 1), 512)

            chunks.append(
                Chunk(
                    id=f"{doc_id}_c{chunk_index}",
                    doc_id=doc_id,
                    page=accum_page,
                    page_end=accum_page,
                    bbox=split_bbox,
                    text=enriched_text,
                    raw_text=split,
                    token_count=tok_count,
                    headings=list(heading_stack),
                    is_table=False,
                    meta=dict(accum_meta),
                )
            )
            chunk_index += 1

        accum_blocks.clear()
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
            breadcrumb = format_breadcrumb(heading_stack, max_tokens_budget=30)
            prefix = f"Table ({breadcrumb}):\n" if breadcrumb else ""
            prefix_tokens = estimate_tokens(prefix) if prefix else 0
            table_budget = max(max_tokens - prefix_tokens - 8, max_tokens // 2)

            table_chunks = split_large_table(block.text, max_tokens=table_budget, overlap_rows=1)
            for t_text in table_chunks:
                enriched_text = f"{prefix}{t_text}" if prefix else t_text
                tok_count = min(max(estimate_tokens(enriched_text), 1), 512)

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
            breadcrumb = format_breadcrumb(heading_stack, max_tokens_budget=30)
            fig_prefix = f"Figure ({breadcrumb}):\n" if breadcrumb else ""
            raw_text = block.text.strip()
            prefix_tokens = estimate_tokens(fig_prefix) if fig_prefix else 0
            fig_budget = max(max_tokens - prefix_tokens - 8, max_tokens // 2)

            fig_splits = (
                split_text_recursive(raw_text, max_tokens=fig_budget, overlap=overlap_tokens)
                if raw_text
                else [""]
            )
            for f_text in fig_splits:
                enriched_text = (
                    f"{fig_prefix}{f_text}"
                    if fig_prefix and f_text
                    else (fig_prefix.rstrip() if fig_prefix else f_text)
                )
                tok_count = min(max(estimate_tokens(enriched_text), 1), 512)

                chunks.append(
                    Chunk(
                        id=f"{doc_id}_c{chunk_index}",
                        doc_id=doc_id,
                        page=block.page,
                        page_end=block.page,
                        bbox=block.bbox,
                        text=enriched_text,
                        raw_text=f_text,
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

            # Flush if page boundary crossed
            if accum_page is not None and accum_page != block.page:
                flush_accumulated_text()

            accum_blocks.append((raw_text, block.bbox))
            accum_page = block.page
            if not accum_meta and block.meta:
                accum_meta = dict(block.meta)

    # Flush remaining text
    flush_accumulated_text()

    # Fallback if document had only headings and no text or table blocks
    if not chunks and heading_stack:
        title_text = " > ".join(heading_stack)
        chunks.append(
            Chunk(
                id=f"{doc_id}_c0",
                doc_id=doc_id,
                page=1,
                page_end=1,
                bbox=(0.0, 0.0, 0.0, 0.0),
                text=title_text,
                raw_text=title_text,
                token_count=min(max(estimate_tokens(title_text), 1), 512),
                headings=list(heading_stack),
                is_table=False,
                meta={},
            )
        )

    logger.info(f"Chunker: generated {len(chunks)} chunks for doc_id='{doc_id}' (max_tokens={max_tokens})")
    return chunks
