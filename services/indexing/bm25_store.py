"""Sparse lexical store powered by bm25s with disk persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.chunk import Chunk
from services.common.logger import get_logger

logger = get_logger("indexing.bm25")

INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "indices" / "bm25"
INDEX_DIR.mkdir(parents=True, exist_ok=True)


class BM25Store:
    """Manages BM25-Okapi indexing and search using the bm25s library."""

    def __init__(self, index_dir: Path | str | None = None) -> None:
        self.index_dir = Path(index_dir) if index_dir else INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.corpus_chunks: list[dict[str, Any]] = []
        self.retriever: Any = None
        self._load_if_exists()

    def _load_if_exists(self) -> None:
        """Loads saved index and corpus metadata from disk if present."""
        metadata_file = self.index_dir / "chunks_metadata.json"
        if metadata_file.exists():
            try:
                import bm25s
                self.retriever = bm25s.BM25.load(str(self.index_dir), load_corpus=False)
                with open(metadata_file, "r", encoding="utf-8") as f:
                    self.corpus_chunks = json.load(f)
                logger.info(f"Loaded existing BM25 index with {len(self.corpus_chunks)} chunks from {self.index_dir}")
            except Exception as e:
                logger.warning(f"Could not load existing BM25 index: {e}")

    def index(self, chunks: list[Chunk]) -> int:
        """Indexes a list of chunks, builds BM25 index, and persists to disk."""
        if not chunks:
            return 0

        import bm25s

        # Deduplicate incoming chunks against existing corpus by chunk id
        existing_ids = {c["id"] for c in self.corpus_chunks}
        new_chunks = [c for c in chunks if c.id not in existing_ids]

        if not new_chunks:
            logger.info("All chunks already present in BM25 index, skipping re-index.")
            return 0

        # Append new chunk dicts
        for c in new_chunks:
            self.corpus_chunks.append({
                "id": c.id,
                "doc_id": c.doc_id,
                "page": c.page,
                "bbox": list(c.bbox),
                "text": c.text,
                "token_count": c.token_count,
                "headings": c.headings,
                "is_table": c.is_table,
            })

        # Re-tokenize and build BM25-Okapi index
        corpus_texts = [c["text"] for c in self.corpus_chunks]
        corpus_tokens = bm25s.tokenize(corpus_texts, stopwords="en")

        # Use default BM25 method (non-negative IDF) and index directly
        self.retriever = bm25s.BM25()
        self.retriever.index(corpus_tokens)

        # Persist to disk
        self.retriever.save(str(self.index_dir))
        metadata_file = self.index_dir / "chunks_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.corpus_chunks, f, indent=2)

        logger.info(f"BM25Store: indexed {len(new_chunks)} new chunks (total {len(self.corpus_chunks)})")
        return len(new_chunks)

    def search(self, query: str, top_k: int = 20) -> list[tuple[dict[str, Any], float]]:
        """Searches BM25 index and returns list of (chunk_dict, score) ranked by relevance."""
        if not self.retriever or not self.corpus_chunks:
            return []

        import bm25s

        query_tokens = bm25s.tokenize([query], stopwords="en")
        k_val = max(1, min(top_k, len(self.corpus_chunks)))
        results, scores = self.retriever.retrieve(query_tokens, k=k_val)

        ranked_results: list[tuple[dict[str, Any], float]] = []
        for idx, score in zip(results[0], scores[0]):
            f_score = float(score)
            if f_score <= 0.0:
                continue
            chunk_data = self.corpus_chunks[int(idx)]
            ranked_results.append((chunk_data, f_score))

        return ranked_results
