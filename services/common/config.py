"""Centralized YAML configuration loader with Pydantic validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"


class HardwareConfig(BaseModel):
    profile: str = "quality"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "llama3.1:latest"
    embedding_model: str = "bge-m3:latest"
    reranker_model: str = "flashrank"
    reranker_device: str = "cpu"


class StorageConfig(BaseModel):
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "postgres"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379

    @property
    def postgres_url(self) -> str:
        pwd = f":{self.postgres_password}" if self.postgres_password else ""
        return f"postgresql://{self.postgres_user}{pwd}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


class IngestionConfig(BaseModel):
    probe_sample_pages: int = 8
    text_coverage_threshold: float = 0.60
    image_ratio_threshold: float = 0.65
    gutter_gap_threshold_pt: float = 18.0


class ChunkingConfig(BaseModel):
    max_tokens: int = 512
    overlap_tokens: int = 64
    preserve_tables: bool = True


class RetrievalConfig(BaseModel):
    top_k: int = 20
    top_rerank: int = 6
    rrf_k: int = 60
    min_score_cutoff: float = 0.15
    collection_name: str = "rag_docs"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    dir: str = "logs"


class AppConfig(BaseModel):
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(profile: str | None = None) -> AppConfig:
    """Loads default.yaml and merges profile overlay (quality/fast) plus environment variables."""
    default_path = CONFIGS_DIR / "default.yaml"
    data: dict[str, Any] = {}

    if default_path.exists():
        with open(default_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Profile selection
    selected_profile = profile or os.environ.get("RAG_PROFILE") or data.get("hardware", {}).get("profile", "quality")
    profile_path = CONFIGS_DIR / "profiles" / f"{selected_profile}.yaml"

    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = yaml.safe_load(f) or {}
            data = _deep_merge(data, profile_data)

    # Environment variable overrides
    storage_data = data.setdefault("storage", {})
    if "POSTGRES_HOST" in os.environ:
        storage_data["postgres_host"] = os.environ["POSTGRES_HOST"]
    if "POSTGRES_PORT" in os.environ:
        storage_data["postgres_port"] = int(os.environ["POSTGRES_PORT"])
    if "POSTGRES_DB" in os.environ:
        storage_data["postgres_db"] = os.environ["POSTGRES_DB"]
    if "POSTGRES_USER" in os.environ:
        storage_data["postgres_user"] = os.environ["POSTGRES_USER"]
    if "POSTGRES_PASSWORD" in os.environ:
        storage_data["postgres_password"] = os.environ["POSTGRES_PASSWORD"]
    if "QDRANT_HOST" in os.environ:
        storage_data["qdrant_host"] = os.environ["QDRANT_HOST"]
    if "QDRANT_PORT" in os.environ:
        storage_data["qdrant_port"] = int(os.environ["QDRANT_PORT"])
    if "REDIS_HOST" in os.environ:
        storage_data["redis_host"] = os.environ["REDIS_HOST"]
    if "REDIS_PORT" in os.environ:
        storage_data["redis_port"] = int(os.environ["REDIS_PORT"])

    hardware_data = data.setdefault("hardware", {})
    if "OLLAMA_BASE_URL" in os.environ:
        hardware_data["ollama_base_url"] = os.environ["OLLAMA_BASE_URL"]

    return AppConfig(**data)
