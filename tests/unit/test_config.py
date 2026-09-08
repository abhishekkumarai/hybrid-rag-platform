"""Unit test for centralized YAML config loader."""

from services.common.config import load_config


def test_load_default_config():
    config = load_config()
    assert config.hardware.profile == "quality"
    assert config.hardware.llm_model == "llama3.1:latest"
    assert config.retrieval.top_k == 20
    assert config.retrieval.min_score_cutoff == 0.15
    assert config.storage.postgres_port == 5432
    assert "postgresql://" in config.storage.postgres_url


def test_load_fast_profile():
    config = load_config(profile="fast")
    assert config.hardware.profile == "fast"
    assert config.hardware.llm_model == "llama3.2:3b"
    assert config.hardware.reranker_model == "flashrank"
