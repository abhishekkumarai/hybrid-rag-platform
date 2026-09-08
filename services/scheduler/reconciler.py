"""Directory reconciliation daemon watching data/documents/ with SHA-256 deduplication."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from services.common.logger import get_logger

logger = get_logger("scheduler.reconciler")

DATA_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "documents"
SEEN_REGISTRY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "seen_documents.json"


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 hash of file content for reliable deduplication."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class DirectoryReconciler:
    """Watches document directory and dispatches unindexed files with deduplication."""

    def __init__(
        self,
        watch_dir: Path | str | None = None,
        registry_file: Path | str | None = None,
    ) -> None:
        self.watch_dir = Path(watch_dir) if watch_dir else DATA_DOCS_DIR
        self.registry_file = Path(registry_file) if registry_file else SEEN_REGISTRY_FILE
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.seen_hashes: dict[str, str] = self._load_registry()

    def _load_registry(self) -> dict[str, str]:
        """Loads {sha256: file_path} registry from disk."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read registry {self.registry_file}: {e}")
        return {}

    def _save_registry(self) -> None:
        """Saves updated seen hashes registry."""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(self.seen_hashes, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save registry {self.registry_file}: {e}")

    def reconcile_once(self, on_new_file: Callable[[Path, str], bool] | None = None) -> list[Path]:
        """Scans directory once and triggers callback on any new, unindexed file."""
        supported_extensions = {".pdf", ".docx", ".txt", ".md"}
        new_files: list[Path] = []

        for item in self.watch_dir.iterdir():
            if item.is_file() and item.suffix.lower() in supported_extensions:
                file_hash = compute_file_sha256(item)

                if file_hash in self.seen_hashes:
                    logger.debug(f"Skipping already-indexed file: {item.name}")
                    continue

                logger.info(f"Discovered new unindexed document: '{item.name}' (hash={file_hash[:8]})")
                success = True
                if on_new_file:
                    success = on_new_file(item, file_hash)

                if success:
                    self.seen_hashes[file_hash] = str(item)
                    new_files.append(item)

        if new_files:
            self._save_registry()
            logger.info(f"Reconciliation completed: indexed {len(new_files)} new documents.")

        return new_files

    def run_daemon(self, interval_sec: int = 60) -> None:
        """Runs periodic scanning loop."""
        logger.info(f"Starting DirectoryReconciler daemon on '{self.watch_dir}' (interval={interval_sec}s)")
        try:
            while True:
                self.reconcile_once()
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            logger.info("Reconciler daemon stopped by user.")


if __name__ == "__main__":
    reconciler = DirectoryReconciler()
    reconciler.run_daemon(interval_sec=60)
