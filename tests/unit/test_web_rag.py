"""Unit tests for Web RAG store, wiki-index parser, indexer, and gateway API (IRA-25, IRA-30)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.document import BlockType
from contracts.retrieval import SearchQuery
from contracts.web import WebSyncRequest
from services.gateway.api import app
from services.indexing.service import IndexingService
from services.indexing.web_indexer import WebRAGIndexer
from services.ingestion.web_parser import WikiIndexWebParser
from services.retrieval.service import RetrievalService

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Artificial Intelligence | Wiki Index</title></head>
<body>
<div id="retype-content">
  <h1 id="artificial-intelligence">Artificial Intelligence</h1>
  <p>Explore the world of community recommended AI and LLM tools.</p>
  <h2 id="ai-chatbots">AI Chatbots</h2>
  <h3 id="official-model-sites">Official Model Sites</h3>
  <ul>
    <li>
      <a href="https://chat.qwen.ai/">Qwen Studio</a> - Qwen3.8 Max / Qwen3.7 Plus / Sign-Up /
      <a href="https://discord.com/invite/CV4E9rpNSD">Discord</a> /
      <a href="https://github.com/QwenLM">GitHub</a>
    </li>
    <li>
      <a href="https://chat.deepseek.com/">DeepSeek</a> - DeepSeek-V4.1-Flash / Unlimited /
      <a href="https://github.com/deepseek-ai">GitHub</a>
    </li>
  </ul>
  <h3 id="local-ai-frontends">Local AI Frontends</h3>
  <ul>
    <li>
      <a href="https://docs.sillytavern.app/">SillyTavern</a> - Desktop LLM Frontend /
      <a href="https://github.com/SillyTavern/SillyTavern">GitHub</a>
    </li>
  </ul>
</div>
</body>
</html>
"""

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://wiki-index.pages.dev/</loc></url>
  <url><loc>https://wiki-index.pages.dev/ai/</loc></url>
  <url><loc>https://wiki-index.pages.dev/developer-tools/</loc></url>
  <url><loc>https://wiki-index.pages.dev/blog/sept-2026/</loc></url>
</urlset>
"""


@pytest.fixture
def mock_html_fetch(monkeypatch):
    """Mocks network requests in WikiIndexWebParser to return synthetic HTML."""
    def fake_fetch_page_html(self, slug_or_url: str, force_refresh: bool = False):
        slug = slug_or_url.strip("/").split("/")[-1] or "ai"
        page_url = f"https://wiki-index.pages.dev/{slug}/"
        return slug, page_url, SAMPLE_HTML

    monkeypatch.setattr(WikiIndexWebParser, "fetch_page_html", fake_fetch_page_html)


def test_wiki_index_parser_blocks_and_resources(mock_html_fetch, tmp_path):
    """Verifies that WikiIndexWebParser extracts structured blocks, breadcrumbs, and link metadata."""
    parser = WikiIndexWebParser(cache_dir=tmp_path)
    doc, blocks = parser.parse_page("ai")

    assert doc.doc_id == "web_wiki_index_ai"
    assert doc.slug == "ai"
    assert "Artificial Intelligence" in doc.title
    assert doc.resource_count == 3
    assert len(blocks) > 0

    # Verify primary resource links and sublinks
    qwen = next(r for r in doc.resources if r.title == "Qwen Studio")
    assert qwen.url == "https://chat.qwen.ai/"
    assert "Official Model Sites" in qwen.section
    assert any("discord" in sl["url"].lower() for sl in qwen.sublinks)
    assert any("github" in sl["url"].lower() for sl in qwen.sublinks)

    deepseek = next(r for r in doc.resources if r.title == "DeepSeek")
    assert deepseek.url == "https://chat.deepseek.com/"

    sillytavern = next(r for r in doc.resources if r.title == "SillyTavern")
    assert sillytavern.url == "https://docs.sillytavern.app/"
    assert "Local AI Frontends" in sillytavern.section

    # Verify blocks have heading and text types
    types = {b.type for b in blocks}
    assert BlockType.HEADING in types
    assert BlockType.TEXT in types

    # Verify web metadata is preserved on text blocks
    text_blocks = [b for b in blocks if b.type == BlockType.TEXT and "Resource:" in b.text]
    assert len(text_blocks) == 3
    assert text_blocks[0].meta.get("is_web") is True
    assert text_blocks[0].meta.get("resource_title") == "Qwen Studio"


def test_wiki_index_parser_sitemap_filtering():
    """Verifies that sitemap parsing filters out blog pages and keeps category slugs."""
    parser = WikiIndexWebParser()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_SITEMAP

    with patch("requests.get", return_value=mock_resp):
        slugs = parser.fetch_sitemap_slugs()
        assert "ai" in slugs
        assert "developer-tools" in slugs
        assert not any("blog" in s for s in slugs)


def test_web_rag_indexer_sync_and_persistence(mock_html_fetch, tmp_path):
    """Verifies that WebRAGIndexer chunks, dual-indexes, and saves metadata & markdown mirrors."""
    indexing_service = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    parser = WikiIndexWebParser(cache_dir=tmp_path / "cache")
    indexer = WebRAGIndexer(
        indexing_service=indexing_service,
        parser=parser,
        web_docs_dir=tmp_path / "web_docs",
    )

    doc, index_resp = indexer.sync_category("ai")
    assert doc.doc_id == "web_wiki_index_ai"
    assert index_resp.indexed_count > 0
    assert index_resp.dense_indexed is True
    assert index_resp.sparse_indexed is True

    # Check persisted metadata and markdown mirror
    json_path = tmp_path / "web_docs" / "web_wiki_index_ai.json"
    md_path = tmp_path / "web_docs" / "web_wiki_index_ai.md"
    assert json_path.exists()
    assert md_path.exists()
    assert "Artificial Intelligence" in md_path.read_text(encoding="utf-8")

    # List sources
    sources = indexer.list_sources()
    assert len(sources) == 1
    assert sources[0].doc_id == "web_wiki_index_ai"
    assert sources[0].resources_count == 3

    # Get source detail
    retrieved = indexer.get_source("web_wiki_index_ai")
    assert retrieved is not None
    assert retrieved.slug == "ai"


def test_web_rag_retrieval_and_link_citations(mock_html_fetch, tmp_path):
    """Verifies that hybrid retrieval surfaces web citations with external URLs and wiki links."""
    indexing_service = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    parser = WikiIndexWebParser(cache_dir=tmp_path / "cache")
    indexer = WebRAGIndexer(
        indexing_service=indexing_service,
        parser=parser,
        web_docs_dir=tmp_path / "web_docs",
    )

    # Sync web category
    indexer.sync_category("ai")

    # Retrieve via RetrievalService
    retrieval = RetrievalService(
        qdrant_store=indexing_service.qdrant,
        bm25_store=indexing_service.bm25,
    )

    res = retrieval.retrieve(SearchQuery(query_text="Where can I find SillyTavern frontend?"))
    assert len(res.candidates) > 0
    assert len(res.citations) > 0

    # Verify citation fields
    top_cite = res.citations[0]
    assert top_cite.is_web is True
    assert "web_wiki_index_ai" in top_cite.doc_id
    assert top_cite.resource_title in ("SillyTavern", "Qwen Studio", "DeepSeek")
    assert top_cite.web_url is not None
    assert "wiki-index.pages.dev" in top_cite.web_url
    assert top_cite.resource_url is not None
    assert top_cite.formatted_badge.startswith("[web_wiki_index_ai:")


def test_gateway_web_rag_endpoints(mock_html_fetch, tmp_path, monkeypatch):
    """Verifies FastAPI gateway endpoints for syncing, listing, and creating preset Web RAG project."""
    indexing_service = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    parser = WikiIndexWebParser(cache_dir=tmp_path / "cache")
    test_indexer = WebRAGIndexer(
        indexing_service=indexing_service,
        parser=parser,
        web_docs_dir=tmp_path / "web_docs",
    )

    # Patch global indexer in api.py
    import services.gateway.api as api_mod
    monkeypatch.setattr(api_mod, "_web_indexer", test_indexer)
    # The web corpus is public to every user (IRA-34); conftest stubs it out by default.
    monkeypatch.setattr(api_mod, "_public_doc_ids", lambda: {s.doc_id for s in test_indexer.list_sources()})

    client = TestClient(app)

    # 1. POST /api/v1/web/sync
    sync_resp = client.post("/api/v1/web/sync", json=WebSyncRequest(categories=["ai"]).model_dump())
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["total_pages"] == 1
    assert sync_data["total_resources"] == 3
    assert "web_wiki_index_ai" in sync_data["synced_pages"]

    # 2. GET /api/v1/web/sources
    sources_resp = client.get("/api/v1/web/sources")
    assert sources_resp.status_code == 200
    sources_data = sources_resp.json()
    assert sources_data["total_sources"] == 1
    assert sources_data["sources"][0]["doc_id"] == "web_wiki_index_ai"

    # 3. GET /api/v1/web/sources/{doc_id}
    detail_resp = client.get("/api/v1/web/sources/web_wiki_index_ai")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["slug"] == "ai"
    assert len(detail_data["resources"]) == 3

    # 4. POST /api/v1/web/preset-project
    preset_resp = client.post("/api/v1/web/preset-project")
    assert preset_resp.status_code == 200
    preset_data = preset_resp.json()
    assert preset_data["title"] == "Wiki Index (Web RAG)"
    assert "web_wiki_index_ai" in preset_data["attached_sources"]

    # 5. GET /api/v1/documents contains web docs
    docs_resp = client.get("/api/v1/documents")
    assert docs_resp.status_code == 200
    docs_list = docs_resp.json()["documents"]
    web_doc_entries = [d for d in docs_list if d.get("is_web") is True]
    assert len(web_doc_entries) >= 1
    assert any(d["doc_id"] == "web_wiki_index_ai" for d in web_doc_entries)

    # 6. GET /api/v1/documents/{doc_id}/raw serves markdown
    raw_resp = client.get("/api/v1/documents/web_wiki_index_ai/raw")
    assert raw_resp.status_code == 200
    assert "text/markdown" in raw_resp.headers.get("content-type", "")
    assert "Artificial Intelligence" in raw_resp.text
