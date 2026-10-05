"""Shared {file_hash: file_path} discovery registry for data/documents/.

Used by the scan activity (to decide what's new) and by the gateway's DLQ replay endpoint (to
recover a failed workflow's original arguments from its id, which embeds the file hash) — see
module docstring in `services.scheduling.client` for why this avoids walking Temporal history.
"""

from __future__ import annotations

import json
from pathlib import Path

from services.common.logger import get_logger

logger = get_logger("scheduling.registry")

DATA_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "documents"
SEEN_REGISTRY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "seen_documents.json"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def load_registry(registry_file: Path | str = SEEN_REGISTRY_FILE) -> dict[str, str]:
    """Loads {sha256: file_path} registry from disk."""
    registry_file = Path(registry_file)
    if registry_file.exists():
        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read registry {registry_file}: {e}")
    return {}


def save_registry(seen: dict[str, str], registry_file: Path | str = SEEN_REGISTRY_FILE) -> None:
    registry_file = Path(registry_file)
    try:
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_file, "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save registry {registry_file}: {e}")
