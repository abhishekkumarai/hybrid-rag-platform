"""Which installed Ollama models can actually answer a chat turn (IRA-31).

`/api/tags` lists every installed model, including the embedding and reranker models retrieval uses.
Offering those as chat models broke every turn of a project that picked one: embedding models make
Ollama return "does not support generate", and the bge reranker crashes Ollama's llama-server process.

Ollama's own `capabilities` are not enough on their own: a model imported from a GGUF can report
`completion` without being a generator (the bge reranker says `completion` and is a `bert` encoder; the
gte-qwen2 embedding model says `completion` on a `qwen2` architecture). So a model counts as a chat
model only if it passes all three checks: capability, architecture, and name.
"""

from __future__ import annotations

import re
import threading

import requests

from services.common.logger import get_logger

logger = get_logger("gateway.model_catalog")

# Encoder architectures produce embeddings or scores, never text.
_ENCODER_ARCH = re.compile(r"bert|roberta|electra", re.I)
# Retrieval-model naming, for models whose metadata claims `completion` (and for Ollama versions that
# report no capabilities at all).
_NON_CHAT_NAME = re.compile(r"embed|rerank|(^|[/_:.-])(bge|gte|e5|minilm|nomic)([/_:.-]|$)", re.I)


def is_chat_model(name: str, show: dict | None = None) -> bool:
    """True when `name` can generate text. `show` is Ollama's /api/show body for it, if available."""
    if _NON_CHAT_NAME.search(name):
        return False
    if not show:
        return True
    capabilities = show.get("capabilities")
    if capabilities is not None and ("completion" not in capabilities or "embedding" in capabilities):
        return False
    architecture = (show.get("model_info") or {}).get("general.architecture") or ""
    return not _ENCODER_ARCH.search(architecture)


class ModelCatalog:
    """Classifies installed models, caching /api/show results by digest (a re-pull re-checks)."""

    def __init__(self, ollama_base_url: str, timeout_s: float = 2.0):
        self.base_url = ollama_base_url
        self.timeout_s = timeout_s
        self._verdicts: dict[str, bool] = {}
        self._lock = threading.Lock()

    def installed(self) -> list[dict] | None:
        """Ollama's /api/tags entries, or None when Ollama is unreachable."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=self.timeout_s)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception as e:
            logger.warning(f"Could not list Ollama models ({self.base_url}): {e}")
            return None

    def _verdict(self, name: str, digest: str | None) -> bool:
        key = f"{name}@{digest}"
        with self._lock:
            if key in self._verdicts:
                return self._verdicts[key]
        show = None
        try:
            r = requests.post(f"{self.base_url}/api/show", json={"model": name}, timeout=self.timeout_s)
            if r.status_code == 200:
                show = r.json()
        except Exception as e:
            logger.warning(f"/api/show failed for {name}; classifying by name only: {e}")
        verdict = is_chat_model(name, show)
        if show is not None:  # only cache real metadata; a transient failure is re-checked next time
            with self._lock:
                self._verdicts[key] = verdict
        return verdict

    def chat_models(self, installed: list[dict] | None = None) -> list[dict] | None:
        """The installed models that can chat, or None when Ollama is unreachable."""
        installed = self.installed() if installed is None else installed
        if installed is None:
            return None
        return [m for m in installed if m.get("name") and self._verdict(m["name"], m.get("digest"))]

    def rejects(self, name: str) -> bool:
        """True only when `name` is installed and known not to chat. Unknown or uninstalled models
        are left to Ollama, so an unreachable catalog never blocks a turn."""
        installed = self.installed()
        if not installed:
            return False
        match = next((m for m in installed if m.get("name") == name), None)
        return match is not None and not self._verdict(name, match.get("digest"))
