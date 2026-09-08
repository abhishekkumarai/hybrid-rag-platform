"""Contextual Compression & Adaptive Token Budget Compactor for Phase 14.

Preserves strict Ollama 8K context envelope (~3,072 token context passages budget)
under deep multi-hop and multi-document queries. Features:
1. Extractive sentence salience selector.
2. Cross-document redundancy deduplication.
3. Selective table column pruning for wide tables.
4. Strict token budget packing preserving bounding box coordinates.
"""

from __future__ import annotations

import math
import re
import time
from typing import Sequence

from contracts.compactor import CompactedContext, CompressedChunk
from contracts.retrieval import Candidate
from services.common.logger import get_logger

logger = get_logger("retrieval.compactor")


def estimate_tokens(text: str) -> int:
    """Fast, accurate token estimation (~1.3 tokens per word)."""
    words = text.split()
    if not words:
        return 0
    return max(1, int(math.ceil(len(words) * 1.3)))


def extract_sentences(text: str) -> list[str]:
    """Splits text into coherent sentence units."""
    # Handle markdown table lines or bullet points separately
    if "|" in text and "-|-" in text:
        # Tables handled by table parser
        return [text]

    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned = [s.strip() for s in raw_sentences if len(s.strip()) > 5]
    return cleaned if cleaned else [text.strip()]


def calculate_jaccard_similarity(s1: str, s2: str) -> float:
    """Calculates word-token Jaccard similarity between two sentences."""
    tokens1 = set(re.findall(r"\b\w{3,}\b", s1.lower()))
    tokens2 = set(re.findall(r"\b\w{3,}\b", s2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


def score_sentence_salience(sentence: str, query: str, candidate_score: float = 0.5) -> float:
    """Scores sentence relevance against the query using term matching and density."""
    sent_lower = sentence.lower()
    query_words = [w.lower() for w in re.findall(r"\b\w{2,}\b", query) if len(w) > 2]
    if not query_words:
        return candidate_score

    matched_words = sum(1 for w in query_words if w in sent_lower)
    overlap_ratio = matched_words / len(query_words)

    # Bonus for numerical metrics or exact phrases
    has_numbers = bool(re.search(r"\b\d+(?:\.\d+)?\b", sent_lower))
    number_bonus = 0.15 if has_numbers else 0.0

    # Base score combines candidate parent score with query overlap
    score = (0.4 * candidate_score) + (0.45 * overlap_ratio) + number_bonus
    return min(1.0, score)


class ContextCompactor:
    """Adaptive Context Compactor for protecting the Ollama 8K context envelope."""

    def __init__(
        self,
        default_budget_tokens: int = 3072,
        min_sentence_score: float = 0.15,
        redundancy_similarity_threshold: float = 0.70,
    ) -> None:
        self.default_budget_tokens = default_budget_tokens
        self.min_sentence_score = min_sentence_score
        self.redundancy_threshold = redundancy_similarity_threshold

    def prune_markdown_table(self, table_text: str, query: str) -> tuple[str, int]:
        """Selectively prunes wide markdown table columns that are irrelevant to query.

        Returns (pruned_table_markdown, pruned_columns_count).
        """
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]
        table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
        if len(table_lines) < 3:
            return table_text, 0

        # Parse header
        header_cells = [c.strip() for c in table_lines[0].strip("|").split("|")]
        if len(header_cells) <= 3:
            # Table is already compact
            return table_text, 0

        num_cols = len(header_cells)
        query_terms = set(re.findall(r"\b\w{3,}\b", query.lower()))

        # Score columns: Column 0 (identifier) is ALWAYS retained
        col_scores: list[float] = [1.0]  # Col 0 gets top score

        for col_idx in range(1, num_cols):
            col_text = header_cells[col_idx].lower()
            # Also sample cell values from subsequent rows
            for row_line in table_lines[2:6]:
                row_cells = [c.strip() for c in row_line.strip("|").split("|")]
                if col_idx < len(row_cells):
                    col_text += " " + row_cells[col_idx].lower()

            matches = sum(1 for term in query_terms if term in col_text)
            score = matches / len(query_terms) if query_terms else 0.5
            col_scores.append(score)

        # Decide which columns to keep: col 0 + top columns
        # Keep at least 2 columns, at most 4
        indexed_scores = list(enumerate(col_scores))
        # Keep col 0 regardless
        kept_indices = {0}

        # Sort remaining by score
        other_cols = sorted(indexed_scores[1:], key=lambda x: x[1], reverse=True)
        for idx, sc in other_cols:
            if sc > 0.0 or len(kept_indices) < 3:
                kept_indices.add(idx)
            if len(kept_indices) >= 4:
                break

        sorted_kept = sorted(list(kept_indices))
        pruned_count = num_cols - len(sorted_kept)
        if pruned_count <= 0:
            return table_text, 0

        # Reconstruct pruned table
        pruned_lines: list[str] = []
        # Header
        new_header = "| " + " | ".join([header_cells[i] for i in sorted_kept]) + " |"
        pruned_lines.append(new_header)
        # Separator
        new_sep = "| " + " | ".join(["---" for _ in sorted_kept]) + " |"
        pruned_lines.append(new_sep)
        # Rows
        for row_line in table_lines[2:]:
            row_cells = [c.strip() for c in row_line.strip("|").split("|")]
            new_row_cells = [row_cells[i] if i < len(row_cells) else "" for i in sorted_kept]
            pruned_lines.append("| " + " | ".join(new_row_cells) + " |")

        return "\n".join(pruned_lines), pruned_count

    def compress_candidates(
        self,
        query: str,
        candidates: Sequence[Candidate],
        budget_tokens: int | None = None,
        deduplicate: bool = True,
        prune_tables: bool = True,
    ) -> CompactedContext:
        """Compresses retrieved candidates to fit strictly within target token budget.

        Preserves provenance coordinates (doc_id, page, bbox) while eliminating filler,
        cross-document redundancy, and excessive table columns.
        """
        start_time = time.perf_counter()
        target_budget = budget_tokens or self.default_budget_tokens

        total_orig_tokens = 0
        accepted_sentences_corpus: list[str] = []
        compressed_chunks: list[CompressedChunk] = []

        total_dedup_sentences = 0
        total_pruned_columns = 0
        dropped_chunks = 0
        accumulated_tokens = 0

        for cand in candidates:
            orig_tokens = estimate_tokens(cand.text)
            total_orig_tokens += orig_tokens

            # Table handling
            if cand.is_table and prune_tables:
                comp_text, pruned_cols = self.prune_markdown_table(cand.text, query)
                total_pruned_columns += pruned_cols
                comp_tokens = estimate_tokens(comp_text)
                ratio = round(comp_tokens / orig_tokens, 2) if orig_tokens > 0 else 1.0

                if accumulated_tokens + comp_tokens <= target_budget:
                    compressed_chunks.append(
                        CompressedChunk(
                            id=cand.id,
                            doc_id=cand.doc_id,
                            page=cand.page,
                            bbox=cand.bbox,
                            original_text=cand.text,
                            compressed_text=comp_text,
                            original_tokens=orig_tokens,
                            compressed_tokens=comp_tokens,
                            compression_ratio=min(1.0, ratio),
                            is_table=True,
                            is_figure=cand.is_figure,
                            headings=cand.headings,
                            retained_sentences=[comp_text],
                            score=cand.rerank_score or cand.rrf_score,
                        )
                    )
                    accumulated_tokens += comp_tokens
                else:
                    dropped_chunks += 1
                continue

            # Prose handling: sentence salience & deduplication
            sentences = extract_sentences(cand.text)
            cand_score = cand.rerank_score or cand.rrf_score

            retained_sentences: list[str] = []
            for sent in sentences:
                # 1. Redundancy check against already accepted sentences
                if deduplicate:
                    is_redundant = False
                    for accepted_sent in accepted_sentences_corpus:
                        sim = calculate_jaccard_similarity(sent, accepted_sent)
                        if sim >= self.redundancy_threshold:
                            is_redundant = True
                            total_dedup_sentences += 1
                            break
                    if is_redundant:
                        continue

                # 2. Salience scoring
                salience = score_sentence_salience(sent, query, candidate_score=cand_score)
                if salience >= self.min_sentence_score:
                    retained_sentences.append(sent)
                    accepted_sentences_corpus.append(sent)

            # Fallback if all sentences were filtered
            if not retained_sentences and sentences:
                best_sent = max(
                    sentences,
                    key=lambda s: score_sentence_salience(s, query, candidate_score=cand_score),
                )
                retained_sentences.append(best_sent)
                accepted_sentences_corpus.append(best_sent)

            compressed_passage = " ".join(retained_sentences)
            comp_tokens = estimate_tokens(compressed_passage)

            # Budget check
            if accumulated_tokens + comp_tokens <= target_budget:
                ratio = round(comp_tokens / orig_tokens, 2) if orig_tokens > 0 else 1.0
                compressed_chunks.append(
                    CompressedChunk(
                        id=cand.id,
                        doc_id=cand.doc_id,
                        page=cand.page,
                        bbox=cand.bbox,
                        original_text=cand.text,
                        compressed_text=compressed_passage,
                        original_tokens=orig_tokens,
                        compressed_tokens=comp_tokens,
                        compression_ratio=min(1.0, ratio),
                        is_table=cand.is_table,
                        is_figure=cand.is_figure,
                        headings=cand.headings,
                        retained_sentences=retained_sentences,
                        score=cand_score,
                    )
                )
                accumulated_tokens += comp_tokens
            elif accumulated_tokens < target_budget:
                # Partial pack: pack only as many sentences as fit
                partial_sents: list[str] = []
                partial_toks = 0
                for s in retained_sentences:
                    s_toks = estimate_tokens(s)
                    if accumulated_tokens + partial_toks + s_toks <= target_budget:
                        partial_sents.append(s)
                        partial_toks += s_toks
                    else:
                        break

                if partial_sents:
                    part_text = " ".join(partial_sents)
                    part_toks = estimate_tokens(part_text)
                    ratio = round(part_toks / orig_tokens, 2) if orig_tokens > 0 else 1.0
                    compressed_chunks.append(
                        CompressedChunk(
                            id=cand.id,
                            doc_id=cand.doc_id,
                            page=cand.page,
                            bbox=cand.bbox,
                            original_text=cand.text,
                            compressed_text=part_text,
                            original_tokens=orig_tokens,
                            compressed_tokens=part_toks,
                            compression_ratio=min(1.0, ratio),
                            is_table=cand.is_table,
                            is_figure=cand.is_figure,
                            headings=cand.headings,
                            retained_sentences=partial_sents,
                            score=cand_score,
                        )
                    )
                    accumulated_tokens += part_toks
                else:
                    dropped_chunks += 1
            else:
                dropped_chunks += 1

        overall_ratio = (
            round(accumulated_tokens / total_orig_tokens, 2) if total_orig_tokens > 0 else 1.0
        )

        # Build formatted prompt context string
        context_blocks = []
        for c in compressed_chunks:
            b = c.bbox
            badge = f"[{c.doc_id}: Page {c.page}, ({b[0]:.1f}, {b[1]:.1f}, {b[2]:.1f}, {b[3]:.1f})]"
            context_blocks.append(f"Source {badge}:\n{c.compressed_text}")

        formatted_context = "\n\n".join(context_blocks)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"ContextCompactor: {len(candidates)} chunks ({total_orig_tokens} tok) -> "
            f"{len(compressed_chunks)} retained ({accumulated_tokens} tok, ratio={overall_ratio:.2f}) "
            f"[deduped {total_dedup_sentences} sents, pruned {total_pruned_columns} cols, dropped {dropped_chunks} chunks] "
            f"in {elapsed_ms:.2f}ms"
        )

        return CompactedContext(
            query=query,
            chunks=compressed_chunks,
            total_original_tokens=total_orig_tokens,
            total_compressed_tokens=accumulated_tokens,
            overall_compression_ratio=overall_ratio,
            budget_tokens=target_budget,
            dropped_chunks_count=dropped_chunks,
            deduplicated_sentences_count=total_dedup_sentences,
            pruned_table_columns_count=total_pruned_columns,
            formatted_prompt_context=formatted_context,
            duration_ms=round(elapsed_ms, 2),
        )
