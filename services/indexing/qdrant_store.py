"""Dense vector store interface for Qdrant with local fallback."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import requests

from contracts.chunk import Chunk
from services.common.logger import get_logger

logger = get_logger("indexing.qdrant")

# Resolved from __file__ (not CWD) so it works regardless of the process's working directory —
# see the CWD-dependent-paths gotcha in CLAUDE.md for why relative `Path("data/...")` is unsafe here.
_HNSW_STATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "hnsw_state.json"


def _load_hnsw_override() -> dict[str, int] | None:
    """Reads the last admin-applied HNSW m/ef_construct, if any, so it survives a process restart."""
    try:
        return json.loads(_HNSW_STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

# Reused across calls so ingesting a document with many chunks doesn't open/tear down a fresh TCP
# (and TLS, where applicable) connection to Ollama per chunk.
_embedding_session = requests.Session()


def get_ollama_embedding(
    text: str,
    model: str = "bge-m3:latest",
    ollama_url: str = "http://127.0.0.1:11434",
    dim: int = 1024,
) -> list[float]:
    """Fetches dense embedding from Ollama; falls back to deterministic hash vector if offline."""
    try:
        res = _embedding_session.post(
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
        host: str | None = None,
        port: int | None = None,
        in_memory: bool = False,
        collection_name: str = "rag_docs",
        vector_dim: int = 1024,
        hnsw_m: int | None = None,
        hnsw_ef_construct: int | None = None,
        default_ef_search: int | None = None,
    ) -> None:
        if host is None or port is None or hnsw_m is None or hnsw_ef_construct is None or default_ef_search is None:
            from services.common.config import load_config
            cfg = load_config()
            if host is None:
                host = cfg.storage.qdrant_host
            if port is None:
                port = cfg.storage.qdrant_port
            if hnsw_m is None:
                hnsw_m = cfg.retrieval.hnsw_m
            if hnsw_ef_construct is None:
                hnsw_ef_construct = cfg.retrieval.hnsw_ef_construct
            if default_ef_search is None:
                default_ef_search = cfg.retrieval.hnsw_ef_search

            # An admin-applied rebuild (update_hnsw_config) overrides the static YAML default so a
            # process restart doesn't silently drop back to configs/default.yaml's m/ef_construct
            # while the actual Qdrant collection is still running the previously-applied values.
            override = _load_hnsw_override()
            if override:
                hnsw_m = override.get("hnsw_m", hnsw_m)
                hnsw_ef_construct = override.get("hnsw_ef_construct", hnsw_ef_construct)

        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self.in_memory = in_memory
        self.host = host
        self.port = port
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct
        self.default_ef_search = default_ef_search

        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

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
                hnsw_config=HnswConfigDiff(m=self.hnsw_m, ef_construct=self.hnsw_ef_construct),
            )
            logger.info(
                f"Created Qdrant collection '{self.collection_name}' (dim={self.vector_dim}, "
                f"m={self.hnsw_m}, ef_construct={self.hnsw_ef_construct})"
            )

    def reset_collection(self) -> None:
        """Deletes and recreates the collection."""
        from qdrant_client.models import Distance, HnswConfigDiff, VectorParams
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=self.hnsw_m, ef_construct=self.hnsw_ef_construct),
        )
        logger.info(f"Reset Qdrant collection '{self.collection_name}'")

    def update_hnsw_config(self, hnsw_m: int, hnsw_ef_construct: int) -> None:
        """Live-updates the collection's HNSW m/ef_construct, triggering Qdrant's background index
        rebuild (existing points are re-indexed in place; nothing is deleted). This is a collection-
        wide, shared-infrastructure change — every workspace's dense retrieval is affected, and the
        rebuild runs asynchronously (see get_index_status for progress). Unlike ef_search, m and
        ef_construct cannot be scoped to a single query or session; Qdrant only supports them at the
        collection level.
        """
        from qdrant_client.models import HnswConfigDiff

        self.client.update_collection(
            collection_name=self.collection_name,
            hnsw_config=HnswConfigDiff(m=hnsw_m, ef_construct=hnsw_ef_construct),
        )
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construct = hnsw_ef_construct

        _HNSW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HNSW_STATE_PATH.write_text(json.dumps({"hnsw_m": hnsw_m, "hnsw_ef_construct": hnsw_ef_construct}))

        logger.info(
            f"QdrantStore: applied HNSW config on '{self.collection_name}' -> "
            f"m={hnsw_m}, ef_construct={hnsw_ef_construct} (background rebuild triggered)"
        )

    def get_index_status(self) -> dict[str, Any]:
        """Reports the live collection's HNSW config and indexing progress for the admin panel."""
        info = self.client.get_collection(self.collection_name)
        return {
            "collection_name": self.collection_name,
            "hnsw_m": self.hnsw_m,
            "hnsw_ef_construct": self.hnsw_ef_construct,
            "default_ef_search": self.default_ef_search,
            "status": str(info.status),
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count,
        }

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
        doc_ids: list[str] | None = None,
        ef_search: int | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Embeds query and searches Qdrant for top_k nearest neighbors with optional doc_ids filter.

        ``ef_search`` overrides the HNSW search-time ef (accuracy/latency trade-off) for this call;
        ``None`` falls back to the instance default set at construction (``default_ef_search``).
        """
        query_vector = get_ollama_embedding(query, ollama_url=ollama_url, dim=self.vector_dim)
        effective_ef_search = ef_search if ef_search is not None else self.default_ef_search

        # 1. Direct REST search for standalone Qdrant (fastest, avoids client 404 retries)
        if not self.in_memory:
            try:
                body: dict[str, Any] = {
                    "vector": query_vector,
                    "limit": top_k,
                    "with_payload": True,
                    "params": {"hnsw_ef": effective_ef_search},
                }
                if doc_ids:
                    body["filter"] = {
                        "should": [{"key": "doc_id", "match": {"value": d}} for d in doc_ids]
                    }
                res = requests.post(
                    f"http://{self.host}:{self.port}/collections/{self.collection_name}/points/search",
                    json=body,
                    timeout=10.0,
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
            q_models_filter = None
            if doc_ids:
                try:
                    from qdrant_client.models import FieldCondition, Filter, MatchValue

                    q_models_filter = Filter(
                        should=[FieldCondition(key="doc_id", match=MatchValue(value=d)) for d in doc_ids]
                    )
                except Exception:
                    pass

            from qdrant_client.models import SearchParams

            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=q_models_filter,
                with_payload=True,
                search_params=SearchParams(hnsw_ef=effective_ef_search),
            ).points

            ranked: list[tuple[dict[str, Any], float]] = []
            for hit in search_result:
                if hit.payload:
                    ranked.append((hit.payload, float(hit.score)))
            return ranked
        except Exception as e:
            logger.debug(f"query_points failed: {e}")

        return []

