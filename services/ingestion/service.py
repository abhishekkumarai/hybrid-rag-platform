"""Ingestion Service API coordinating layout probing and parser execution."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from contracts.document import IngestRequest, IngestResponse
from services.common.logger import get_logger
from services.ingestion.parsers.fast_text import FastTextParser
from services.ingestion.parsers.layout import LayoutParser
from services.ingestion.parsers.ocr import OCRParser
from services.ingestion.probe import probe_document

logger = get_logger("ingestion.service")


class IngestionService:
    """Decoupled service for document probing, routing, and block extraction."""

    def __init__(self) -> None:
        self.fast_parser = FastTextParser()
        self.layout_parser = LayoutParser()
        self.ocr_parser = OCRParser()

    def _generate_doc_id(self, path: Path) -> str:
        """Generates a stable document ID using filename stem and file content hash."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        short_hash = hasher.hexdigest()[:8]
        clean_name = path.stem.replace(" ", "_").lower()
        return f"{clean_name}_{short_hash}"

    def parse(self, request: IngestRequest) -> IngestResponse:
        start_time = time.perf_counter()
        file_path = Path(request.file_path)

        if not file_path.exists():
            duration_ms = (time.perf_counter() - start_time) * 1000
            err_msg = f"File not found: {file_path}"
            logger.error(err_msg)
            raise FileNotFoundError(err_msg)

        doc_id = request.doc_id or self._generate_doc_id(file_path)

        # 1. Run Layout Probe
        profile = probe_document(file_path)

        # 2. Determine Route (override takes precedence)
        selected_route = request.profile_override or profile.route

        logger.info(
            f"Ingesting '{file_path.name}' [doc_id={doc_id}]: route='{selected_route}' (probe='{profile.route}')"
        )

        # 3. Execute Parser based on route
        if selected_route == "layout":
            blocks = self.layout_parser.parse(str(file_path), doc_id)
        elif selected_route == "ocr":
            blocks = self.ocr_parser.parse(str(file_path), doc_id)
        else:
            blocks = self.fast_parser.parse(str(file_path), doc_id)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"Successfully parsed '{file_path.name}' into {len(blocks)} blocks "
            f"via '{selected_route}' in {duration_ms:.2f}ms"
        )

        return IngestResponse(
            doc_id=doc_id,
            file_path=str(file_path),
            profile=profile,
            blocks=blocks,
            duration_ms=round(duration_ms, 2),
        )
