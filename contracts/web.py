"""Data contracts for Web RAG store and wiki-index crawler (IRA-25, IRA-26)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebResourceLink(BaseModel):
    """A curated web resource extracted from wiki-index with external and wiki provenance."""
    title: str = Field(description="Name or title of the resource / tool")
    url: str = Field(description="Primary external URL to the resource")
    description: str = Field(default="", description="Description, feature tags, or model specs")
    wiki_url: str = Field(description="Source wiki-index page or section anchor URL")
    category: str = Field(default="", description="Category slug or name (e.g. ai, video, audio)")
    section: str = Field(default="", description="Section heading under which the link was found")
    sublinks: list[dict[str, str]] = Field(
        default_factory=list,
        description="Auxiliary links associated with the resource (GitHub, Discord, Reddit, Docs)",
    )


class WebPageDocument(BaseModel):
    """Parsed web page document from wiki-index.pages.dev."""
    url: str = Field(description="Full URL of the parsed wiki page")
    slug: str = Field(description="Page slug identifier (e.g. ai, video, developer-tools)")
    doc_id: str = Field(description="Normalized document ID in the RAG store (e.g. web_wiki_index_ai)")
    title: str = Field(description="Title of the wiki page")
    category: str = Field(description="Category classification")
    resource_count: int = Field(default=0, ge=0, description="Total resource links extracted")
    blocks_count: int = Field(default=0, ge=0, description="Total layout blocks generated")
    resources: list[WebResourceLink] = Field(default_factory=list, description="Extracted resource links")
    last_synced: str | None = Field(default=None, description="ISO timestamp of last sync")
    source: str = Field(default="web_wiki_index", description="Source system identifier")


class WebSyncRequest(BaseModel):
    """Request payload to sync wiki-index pages into the RAG store."""
    categories: list[str] | None = Field(
        default=None,
        description="List of category slugs to sync (e.g. ['ai', 'developer-tools']). If None, syncs standard categories.",
    )
    force_refresh: bool = Field(
        default=False,
        description="Whether to re-fetch and re-index already ingested pages",
    )


class WebSyncResponse(BaseModel):
    """Response payload for Web RAG synchronization."""
    synced_pages: list[str] = Field(description="List of synced page slugs or doc_ids")
    total_pages: int = Field(ge=0, description="Count of pages processed")
    total_resources: int = Field(ge=0, description="Count of resource links indexed")
    total_chunks: int = Field(ge=0, description="Count of chunks indexed across dense/sparse/graph")
    duration_ms: float = Field(ge=0.0, description="Total duration in milliseconds")
    status: str = Field(default="completed", description="Status outcome ('completed', 'partial', 'failed')")
    error: str | None = Field(default=None, description="Error message if sync failed")


class WebSourceItem(BaseModel):
    """Summary metadata for an indexed web source document."""
    doc_id: str = Field(description="Document ID in RAG store")
    title: str = Field(description="Document title")
    category: str = Field(description="Category tag")
    url: str = Field(description="Original web URL")
    resources_count: int = Field(default=0, ge=0, description="Number of curated resource links")
    chunks_count: int = Field(default=0, ge=0, description="Number of indexed chunks")
    last_synced: str | None = Field(default=None, description="Last sync timestamp")


class WebSourcesListResponse(BaseModel):
    """Response payload listing all indexed web sources."""
    sources: list[WebSourceItem] = Field(default_factory=list, description="List of indexed web sources")
    total_sources: int = Field(ge=0, description="Total web sources count")
    total_resources: int = Field(ge=0, description="Total resource links across all web sources")
    base_url: str = Field(default="https://wiki-index.pages.dev", description="Base URL of wiki-index")


class WebPresetProjectRequest(BaseModel):
    """Request to create or update a dedicated Wiki Index Web RAG project workspace."""
    title: str = Field(default="Wiki Index (Web RAG)", description="Title for the session/project")
    categories: list[str] | None = Field(
        default=None,
        description="Optional list of categories to attach. Defaults to all synced web sources.",
    )


class WebPresetProjectResponse(BaseModel):
    """Response from creating/updating the Web RAG preset project."""
    session_id: str = Field(description="Session/Project identifier")
    title: str = Field(description="Project title")
    attached_sources: list[str] = Field(description="List of attached web document IDs")
    created: bool = Field(description="True if newly created, False if existing updated")
