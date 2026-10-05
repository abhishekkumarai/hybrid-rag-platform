"""Per-model request fields for Ollama's /api/generate.

Reasoning models (qwen3.5, deepseek-r1, ...) report the `thinking` capability and, by default, spend
the token budget on a separate `thinking` stream before writing `response`. With this app's small
`num_predict` that leaves an empty or truncated answer, and the reasoning is not wanted in a grounded,
cited answer anyway. `think: false` turns it off -- but Ollama rejects the field for models that do not
support thinking (llama3.x), so it is only sent to models that advertise the capability.
"""

from __future__ import annotations

import threading

import requests

from services.common.logger import get_logger

logger = get_logger("common.ollama_options")

_thinking: dict[tuple[str, str], bool] = {}
_lock = threading.Lock()


def supports_thinking(base_url: str, model: str, timeout_s: float = 2.0) -> bool:
    """True when Ollama lists `thinking` among the model's capabilities. Unknown -> False, so a
    failed lookup never adds a field a plain model would reject; only real answers are cached."""
    key = (base_url, model)
    with _lock:
        if key in _thinking:
            return _thinking[key]
    try:
        r = requests.post(f"{base_url}/api/show", json={"model": model}, timeout=timeout_s)
        if r.status_code != 200:
            return False
        caps = r.json().get("capabilities")
        verdict = isinstance(caps, list) and "thinking" in caps
    except Exception as e:
        logger.warning(f"/api/show failed for {model}; not disabling thinking: {e}")
        return False
    with _lock:
        _thinking[key] = verdict
    return verdict


def no_think(base_url: str, model: str) -> dict:
    """Extra /api/generate body fields: `{"think": False}` for reasoning models, else `{}`."""
    return {"think": False} if supports_thinking(base_url, model) else {}
