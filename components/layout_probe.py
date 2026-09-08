"""Langflow custom component for layout-aware document ingestion."""

from __future__ import annotations

from typing import Any

from contracts.document import IngestRequest
from services.common.logger import get_logger
from services.ingestion.service import IngestionService

logger = get_logger("components.layout_probe")

# Attempt Langflow Component import; fallback to plain Python class for unit tests
try:
    from langflow.custom import Component
    from langflow.io import DropdownInput, FileInput, Output
    _HAS_LANGFLOW = True
except ImportError:
    _HAS_LANGFLOW = False
    Component = object  # type: ignore


class LayoutProbeComponent(Component):
    display_name = "Layout Ingestion Router"
    description = "8-page PyMuPDF sampling heuristic routing to fast_text, layout, or ocr."
    icon = "file-search"
    beta = True

    if _HAS_LANGFLOW:
        inputs = [
            FileInput(
                name="file_path",
                display_name="Document File",
                info="Upload PDF or enter document file path",
                file_types=["pdf"],
                required=True,
            ),
            DropdownInput(
                name="profile_override",
                display_name="Profile Override",
                options=["auto", "fast_text", "layout", "ocr"],
                value="auto",
            ),
        ]
        outputs = [
            Output(name="blocks_data", display_name="Extracted Blocks", method="extract_blocks"),
            Output(name="route_info", display_name="Route Profile", method="get_route_info"),
        ]

    def __init__(self, **kwargs: Any) -> None:
        if _HAS_LANGFLOW:
            super().__init__(**kwargs)
        self.service = IngestionService()

    def extract_blocks(self, file_path: str = "", profile_override: str = "auto") -> list[dict[str, Any]]:
        override = None if profile_override == "auto" else profile_override
        req = IngestRequest(file_path=file_path, profile_override=override)
        res = self.service.parse(req)
        return [b.model_dump() for b in res.blocks]

    def get_route_info(self, file_path: str = "", profile_override: str = "auto") -> dict[str, Any]:
        override = None if profile_override == "auto" else profile_override
        req = IngestRequest(file_path=file_path, profile_override=override)
        res = self.service.parse(req)
        return res.profile.model_dump()
