"""Web connector contracts (IRA-57): a website crawled, parsed and kept in sync as indexed documents."""

from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field

RenderMode = Literal["auto", "static", "browser"]
Schedule = Literal["manual", "daily", "weekly"]
SyncStatus = Literal["idle", "queued", "running", "ok", "partial", "error"]
PageStatus = Literal["indexed", "unchanged", "skipped", "needs_js", "error", "removed"]


class CrawlScope(BaseModel):
    """Which pages of the site a connector may fetch."""

    path_prefix: str = Field(default="/", description="Only URLs whose path starts with this are crawled")
    max_pages: int = Field(default=100, ge=1, le=2000)
    max_depth: int = Field(default=3, ge=0, le=10, description="Link hops from the start URL (0 = start page only)")
    include_subdomains: bool = False
    use_sitemap: bool = True
    exclude_patterns: list[str] = Field(
        default_factory=list, description="Substrings; a URL containing any of them is skipped (e.g. '/tag/', '?page=')"
    )


class WebConnector(BaseModel):
    """A website a user connected. Its pages are indexed as documents the owner can read."""

    id: str = Field(default_factory=lambda: f"conn_{uuid.uuid4().hex[:12]}")
    name: str
    start_url: str
    owner_id: str
    workspace_id: str | None = None
    project_id: str | None = Field(default=None, description="Project whose sources follow this site's pages")
    scope: CrawlScope = Field(default_factory=CrawlScope)
    render: RenderMode = Field(default="auto", description="auto: static HTML, headless browser only when needed")
    schedule: Schedule = "manual"
    status: SyncStatus = "idle"
    last_sync_at: float | None = None
    last_sync_duration_s: float | None = None
    next_sync_at: float | None = None
    page_count: int = 0
    last_error: str | None = None
    created_at: float = Field(default_factory=time.time)


class ConnectorPage(BaseModel):
    """One crawled page of a connector and the document it became."""

    url: str
    title: str = ""
    doc_id: str | None = None
    content_hash: str | None = None
    status: PageStatus = "indexed"
    rendered_with: Literal["static", "browser", "pdf"] = "static"
    blocks: int = 0
    words: int = 0
    depth: int = 0
    fetched_at: float = Field(default_factory=time.time)
    changed_at: float | None = None
    error: str | None = None


class SyncReport(BaseModel):
    connector_id: str
    started_at: float
    finished_at: float
    pages_seen: int = 0
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: int = 0
    needs_js: int = 0
    errors: int = 0
    status: SyncStatus = "ok"


class CreateConnectorRequest(BaseModel):
    start_url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)
    workspace_id: str | None = None
    project_id: str | None = None
    scope: CrawlScope | None = None
    render: RenderMode = "auto"
    schedule: Schedule = "manual"
    sync_now: bool = True


class UpdateConnectorRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    project_id: str | None = None
    scope: CrawlScope | None = None
    render: RenderMode | None = None
    schedule: Schedule | None = None


class ConnectorListResponse(BaseModel):
    connectors: list[WebConnector]


class ConnectorDetailResponse(BaseModel):
    connector: WebConnector
    pages: list[ConnectorPage]
    last_report: SyncReport | None = None
