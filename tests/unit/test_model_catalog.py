"""Chat-capable model filtering (IRA-31).

The /api/show fixtures are trimmed copies of what this machine's Ollama returned for each model.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.gateway.model_catalog import ModelCatalog, is_chat_model

SHOW = {
    "llama3.2:3b": {"capabilities": ["completion", "tools"], "model_info": {"general.architecture": "llama"}},
    "deepseek-r1:14b": {"capabilities": ["tools", "thinking", "completion"],
                        "model_info": {"general.architecture": "qwen2"}},
    "bge-m3:latest": {"capabilities": ["embedding"], "model_info": {"general.architecture": "bert"}},
    # Claims `completion` but is a bert cross-encoder; generating with it crashed Ollama's runner.
    "qllama/bge-reranker-v2-m3:latest": {"capabilities": ["completion"],
                                         "model_info": {"general.architecture": "bert"}},
    # Claims `completion` on a decoder architecture; only its name gives it away.
    "aroxima/gte-qwen2-1.5b-instruct:latest": {"capabilities": ["completion"],
                                               "model_info": {"general.architecture": "qwen2"}},
    "hf.co/jinaai/jina-embeddings-v5-text-small-retrieval-GGUF:Q4_K_M": {
        "capabilities": ["embedding", "tools", "thinking"], "model_info": {"general.architecture": "qwen3"}},
}


@pytest.mark.parametrize("name,expected", [
    ("llama3.2:3b", True),
    ("deepseek-r1:14b", True),
    ("bge-m3:latest", False),
    ("qllama/bge-reranker-v2-m3:latest", False),
    ("aroxima/gte-qwen2-1.5b-instruct:latest", False),
    ("hf.co/jinaai/jina-embeddings-v5-text-small-retrieval-GGUF:Q4_K_M", False),
])
def test_is_chat_model_on_real_metadata(name, expected):
    assert is_chat_model(name, SHOW[name]) is expected


def test_is_chat_model_by_name_when_metadata_is_missing():
    assert is_chat_model("nomic-embed-text:latest") is False
    assert is_chat_model("qllama/bge-large-en-v1.5:latest") is False
    assert is_chat_model("llama3.1:latest") is True
    assert is_chat_model("gemma4:e2b") is True  # "e2b" must not trip the e5 rule
    assert is_chat_model("qwen3.5:4b") is True


def _ollama(tags):
    def post(url, json=None, timeout=None):
        return MagicMock(status_code=200, json=MagicMock(return_value=SHOW[json["model"]]))
    get = MagicMock(return_value=MagicMock(json=MagicMock(return_value={"models": tags})))
    return get, MagicMock(side_effect=post)


def test_catalog_lists_only_chat_models_and_caches_by_digest():
    tags = [{"name": n, "digest": f"d-{i}"} for i, n in enumerate(SHOW)]
    get, post = _ollama(tags)
    with patch("services.gateway.model_catalog.requests.get", get), \
         patch("services.gateway.model_catalog.requests.post", post):
        catalog = ModelCatalog("http://ollama")
        assert [m["name"] for m in catalog.chat_models()] == ["llama3.2:3b", "deepseek-r1:14b"]
        catalog.chat_models()
    assert post.call_count == len(SHOW)  # the second listing hit the cache


def test_catalog_rejects_only_installed_non_chat_models():
    tags = [{"name": n, "digest": "x"} for n in SHOW]
    get, post = _ollama(tags)
    with patch("services.gateway.model_catalog.requests.get", get), \
         patch("services.gateway.model_catalog.requests.post", post):
        catalog = ModelCatalog("http://ollama")
        assert catalog.rejects("qllama/bge-reranker-v2-m3:latest") is True
        assert catalog.rejects("llama3.2:3b") is False
        assert catalog.rejects("not-installed:1b") is False  # left for Ollama to report


def test_catalog_never_blocks_when_ollama_is_unreachable():
    with patch("services.gateway.model_catalog.requests.get", side_effect=ConnectionError("down")):
        catalog = ModelCatalog("http://ollama")
        assert catalog.chat_models() is None
        assert catalog.rejects("bge-m3:latest") is False
