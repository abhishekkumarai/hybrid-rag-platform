"""Data contracts for Document Ingestion and Layout Probing service."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    CODE = "code"
    IMAGE = "image"
    CAPTION = "caption"


class Block(BaseModel):
    """Normalized atomic layout block extracted from a document page."""
    id: str = Field(description="Unique block identifier (doc_id_p{page}_b{order})")
    doc_id: str = Field(description="Identifier of the source document")
    page: int = Field(ge=1, description="1-indexed page number")
    bbox: tuple[float, float, float, float] = Field(
        description="Bounding box coordinates (x0, y0, x1, y1) in 72dpi PDF points"
    )
    type: BlockType = Field(default=BlockType.TEXT, description="Block content classification")
    text: str = Field(description="Raw or normalized text content")
    html: str | None = Field(default=None, description="HTML representation for tables")
    image_path: str | None = Field(default=None, description="Path to extracted raster image for figures")
    caption: str | None = Field(default=None, description="Caption or title for table or figure")
    level: int | None = Field(default=None, ge=1, le=6, description="Heading level 1-6 if heading")
    order: int = Field(ge=0, description="Reading order index within the page")
    meta: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class DocumentProfile(BaseModel):
    """Profile metrics computed by the 8-page heuristic layout probe."""
    route: Literal["fast_text", "layout", "ocr"] = Field(description="Selected parsing engine")
    page_count: int = Field(ge=0, description="Total document pages")
    sample_pages: list[int] = Field(description="Page numbers sampled by the probe (max 8)")
    text_coverage: float = Field(ge=0.0, le=1.0, description="Average character-bearing area ratio")
    chars_per_page: float = Field(ge=0.0, description="Average characters per page")
    image_ratio: float = Field(ge=0.0, le=1.0, description="Area occupied by bitmap images")
    columns: int = Field(ge=1, default=1, description="Estimated column count")
    table_score: float = Field(ge=0.0, le=1.0, description="Score based on vector lines and tabular layout")
    reason: str = Field(description="Explanation for the routing decision")


class IngestRequest(BaseModel):
    """Request payload for IngestionService.parse."""
    file_path: str = Field(description="Absolute or relative path to the document file")
    profile_override: Literal["fast_text", "layout", "ocr"] | None = Field(
        default=None, description="Force a specific parser route bypassing probe"
    )
    doc_id: str | None = Field(default=None, description="Optional custom document ID")


class IngestResponse(BaseModel):
    """Response payload returned by IngestionService.parse."""
    doc_id: str = Field(description="Unique document identifier")
    file_path: str = Field(description="Path to processed document")
    profile: DocumentProfile = Field(description="Profile determined by probe")
    blocks: list[Block] = Field(default_factory=list, description="Extracted layout blocks")
    duration_ms: float = Field(ge=0.0, description="Total processing time in milliseconds")
    error: str | None = Field(default=None, description="Error message if parsing failed")
