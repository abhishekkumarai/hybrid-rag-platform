"""Dense vector store interface for Qdrant with local fallback."""

from __future__ import annotations

import math
from typing import Any

import requests

from contracts.chunk import Chunk
from services.common.logger import get_logger

logger = get_logger("indexing.qdrant")


def get_ollama_embedding(
    text: str,
    model: str = "bge-m3:latest",
    ollama_url: str = "http://127.0.0.1:11434",
    dim: int = 1024,
) -> list[float]:
    """Fetches dense embedding from Ollama; falls back to deterministic hash vector if offline."""
    try:
        res = requests.post(
            f"{ollama_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=10.0,
        )
        if res.status_code == 200:
            return res.json().get("embedding", [])
    except Exception:
        pass

    # Deterministic pseudo-embedding for testing or when Ollama is stopped
    import hashlib
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [((b / 255.0) * 2.0 - 1.0) for b in h]
    # Tile to target dimension
    repeated = (vec * (math.ceil(dim / len(vec))))[:dim]
    norm = math.sqrt(sum(x * x for x in repeated)) or 1.0
    return [x / norm for x in repeated]


class QdrantStore:
    """Manages dense vector storage and HNSW similarity search via Qdrant."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6333,
        in_memory: bool = False,
        collection_name: str = "rag_docs",
        vector_dim: int = 1024,
    ) -> None:
        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self.in_memory = in_memory
        self.host = host
        self.port = port

        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        if in_memory:
            self.client = QdrantClient(":memory:")
            logger.info("Initialized QdrantStore in-memory")
        else:
            try:
                self.client = QdrantClient(host=host, port=port, timeout=10.0, check_compatibility=False)
                # Test connection
                self.client.get_collections()
                logger.info(f"Connected to Qdrant at {host}:{port}")
            except Exception as e:
                logger.warning(f"Could not connect to Qdrant at {host}:{port} ({e}); falling back to in-memory store")
                self.client = QdrantClient(":memory:")
                self.in_memory = True

        # Ensure collection exists
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection '{self.collection_name}' (dim={self.vector_dim})")

    def reset_collection(self) -> None:
        """Deletes and recreates the collection."""
        from qdrant_client.models import Distance, VectorParams
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
        )
        logger.info(f"Reset Qdrant collection '{self.collection_name}'")

    def index(self, chunks: list[Chunk], ollama_url: str = "http://127.0.0.1:11434") -> int:
        """Embeds and upserts chunks into Qdrant."""
        if not chunks:
            return 0

        from qdrant_client.models import PointStruct

        points: list[PointStruct] = []
        for idx, chunk in enumerate(chunks):
            vector = get_ollama_embedding(chunk.text, ollama_url=ollama_url, dim=self.vector_dim)
            payload = {
                "id": chunk.id,
                "doc_id": chunk.doc_id,
                "page": chunk.page,
                "bbox": list(chunk.bbox),
                "text": chunk.text,
                "token_count": chunk.token_count,
                "headings": chunk.headings,
                "is_table": chunk.is_table,
                "is_figure": getattr(chunk, "is_figure", False),
                "image_path": getattr(chunk, "image_path", None),
                "caption": getattr(chunk, "caption", None),
                "table_markdown": getattr(chunk, "table_markdown", None),
            }
            # Use deterministic integer or UUID hash for point ID
            import uuid
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.id))
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info(f"QdrantStore: upserted {len(points)} vectors into '{self.collection_name}'")
        return len(points)

    def search(
        self,
        query: str,
        top_k: int = 20,
        ollama_url: str = "http://127.0.0.1:11434",
    ) -> list[tuple[dict[str, Any], float]]:
        """Embeds query and searches Qdrant for top_k nearest neighbors."""
        query_vector = get_ollama_embedding(query, ollama_url=ollama_url, dim=self.vector_dim)

        # 1. Direct REST search for standalone Qdrant (fastest, avoids client 404 retries)
        if not self.in_memory:
            try:
                res = requests.post(
                    f"http://{self.host}:{self.port}/collections/{self.collection_name}/points/search",
                    json={"vector": query_vector, "limit": top_k, "with_payload": True},
                    timeout=5.0,
                )
                if res.status_code == 200:
                    data = res.json().get("result", [])
                    ranked_rest: list[tuple[dict[str, Any], float]] = []
                    for hit in data:
                        payload = hit.get("payload", {})
                        score = float(hit.get("score", 0.0))
                        ranked_rest.append((payload, score))
                    return ranked_rest
            except Exception as e:
                logger.debug(f"Direct REST points/search failed ({e}), falling back to query_points")

        # 2. In-memory or fallback query_points (Qdrant >= 1.10)
        try:
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                with_payload=True,
            ).points

            ranked: list[tuple[dict[str, Any], float]] = []
            for hit in search_result:
                if hit.payload:
                    ranked.append((hit.payload, float(hit.score)))
            return ranked
        except Exception as e:
            logger.debug(f"query_points failed: {e}")

        return []
