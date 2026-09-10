"""Indexing Service coordinating content-aware chunking and dual storage."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from contracts.chunk import IndexRequest, IndexResponse
from contracts.document import Block
from services.common.logger import get_logger
from services.graph.neo4j_store import Neo4jGraphStore
from services.graph.store import GraphStore
from services.indexing.bm25_store import BM25Store
from services.indexing.chunker import chunk_blocks
from services.indexing.qdrant_store import QdrantStore

logger = get_logger("indexing.service")


class IndexingService:
    """Decoupled service for chunking and multi-tier indexing (dense, sparse, graph)."""

    def __init__(
        self,
        qdrant_host: str | None = None,
        qdrant_port: int | None = None,
        in_memory: bool = False,
        bm25_dir: Path | str | None = None,
        max_tokens: int = 512,
        graph_store: Any | None = None,
    ) -> None:
        from services.common.config import load_config
        cfg = load_config()

        if qdrant_host is None:
            qdrant_host = cfg.storage.qdrant_host
        if qdrant_port is None:
            qdrant_port = cfg.storage.qdrant_port

        self.max_tokens = max_tokens
        self.qdrant = QdrantStore(host=qdrant_host, port=qdrant_port, in_memory=in_memory)
        self.bm25 = BM25Store(index_dir=bm25_dir)
        self.graph = graph_store or Neo4jGraphStore(
            uri=cfg.storage.neo4j_uri,
            user=cfg.storage.neo4j_user,
            password=cfg.storage.neo4j_password,
            database=cfg.storage.neo4j_database,
            fallback_store=GraphStore(auto_load=not in_memory),
        )

    def chunk_and_index(self, doc_id: str, blocks: list[Block]) -> IndexResponse:
        """Chunks document blocks and indexes them into dense, sparse, and graph stores."""
        start = time.perf_counter()

        # 1. Content-Aware Chunking
        chunks = chunk_blocks(blocks, doc_id=doc_id, max_tokens=self.max_tokens)

        # 2. Dense Indexing (Qdrant)
        dense_count = self.qdrant.index(chunks)

        # 3. Sparse Indexing (BM25s)
        sparse_count = self.bm25.index(chunks)

        # 4. Knowledge Graph Indexing (Entities & Relations)
        ent_count, rel_count = self.graph.index_chunks(chunks)
        if not self.qdrant.in_memory:
            self.graph.save_to_disk()

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"IndexingService: doc_id='{doc_id}' -> {len(chunks)} chunks indexed "
            f"(dense={dense_count}, sparse={sparse_count}, graph={ent_count} ents/{rel_count} rels) "
            f"in {duration_ms:.2f}ms"
        )

        return IndexResponse(
            doc_id=doc_id,
            indexed_count=len(chunks),
            dense_indexed=dense_count > 0 or len(chunks) == 0,
            sparse_indexed=sparse_count > 0 or len(chunks) == 0,
            graph_indexed=True,
            duration_ms=round(duration_ms, 2),
        )

    def index(self, request: IndexRequest) -> IndexResponse:
        """Indexes pre-chunked items directly."""
        start = time.perf_counter()

        _ = self.qdrant.index(request.chunks)
        _ = self.bm25.index(request.chunks)
        _ = self.graph.index_chunks(request.chunks)
        if not self.qdrant.in_memory:
            self.graph.save_to_disk()

        duration_ms = (time.perf_counter() - start) * 1000

        return IndexResponse(
            doc_id=request.doc_id,
            indexed_count=len(request.chunks),
            dense_indexed=True,
            sparse_indexed=True,
            graph_indexed=True,
            duration_ms=round(duration_ms, 2),
        )
