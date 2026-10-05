"""Reasoning models get `think: false`; plain models must not receive the field."""
from unittest.mock import MagicMock, patch

from services.common import ollama_options


def _show(caps):
    r = MagicMock(status_code=200)
    r.json.return_value = {"capabilities": caps}
    return r


def setup_function():
    ollama_options._thinking.clear()


def test_thinking_model_gets_think_false():
    with patch("services.common.ollama_options.requests.post", return_value=_show(["completion", "thinking"])):
        assert ollama_options.no_think("http://o", "qwen3.5:4b") == {"think": False}


def test_plain_model_gets_nothing():
    with patch("services.common.ollama_options.requests.post", return_value=_show(["completion"])):
        assert ollama_options.no_think("http://o", "llama3.1:latest") == {}


def test_lookup_failure_is_not_cached_and_adds_nothing():
    with patch("services.common.ollama_options.requests.post", side_effect=OSError("down")):
        assert ollama_options.no_think("http://o", "qwen3.5:4b") == {}
    with patch("services.common.ollama_options.requests.post", return_value=_show(["thinking"])):
        assert ollama_options.no_think("http://o", "qwen3.5:4b") == {"think": False}
