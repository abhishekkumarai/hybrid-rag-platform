"""Web RAG Indexer coordinating parsing, dual indexing, and metadata persistence (IRA-25, IRA-27)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from contracts.chunk import IndexResponse
from contracts.document import Block
from contracts.web import WebPageDocument, WebSourceItem, WebSyncResponse
from services.common.logger import get_logger
from services.indexing.service import IndexingService
from services.ingestion.web_parser import DEFAULT_CATEGORIES, WikiIndexWebParser

logger = get_logger("indexing.web_indexer")


class WebRAGIndexer:
    """Indexes crawled wiki-index web documents into Qdrant, BM25, and Knowledge Graph."""

    def __init__(
        self,
        indexing_service: IndexingService | None = None,
        parser: WikiIndexWebParser | None = None,
        web_docs_dir: Path | str | None = None,
    ) -> None:
        self.indexing_service = indexing_service or IndexingService()
        self.parser = parser or WikiIndexWebParser()
        self.web_docs_dir = Path(web_docs_dir or "data/web_documents")
        self.web_docs_dir.mkdir(parents=True, exist_ok=True)

    def sync_category(
        self,
        category_or_slug: str,
        force_refresh: bool = False,
    ) -> tuple[WebPageDocument, IndexResponse]:
        """Parses a category from wiki-index and indexes its blocks into dense, sparse, and graph stores."""
        t0 = time.perf_counter()
        doc, blocks = self.parser.parse_page(category_or_slug, force_refresh=force_refresh)

        # Index blocks into Qdrant, BM25, and Graph
        index_resp = self.indexing_service.chunk_and_index(doc_id=doc.doc_id, blocks=blocks)

        # Persist structured document metadata
        meta_path = self.web_docs_dir / f"{doc.doc_id}.json"
        meta_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")

        # Persist human-readable Markdown mirror
        self._write_markdown_mirror(doc, blocks)

        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"WebRAGIndexer synced category='{doc.category}' (doc_id='{doc.doc_id}'): "
            f"{doc.resource_count} resources, {index_resp.indexed_count} chunks in {ms:.1f}ms"
        )
        return doc, index_resp

    def sync_categories(
        self,
        categories: list[str] | None = None,
        force_refresh: bool = False,
        max_pages: int | None = None,
    ) -> WebSyncResponse:
        """Syncs multiple or all standard wiki-index categories into the RAG store."""
        t0 = time.perf_counter()
        targets = categories if (categories and len(categories) > 0) else list(DEFAULT_CATEGORIES)
        if max_pages and max_pages > 0:
            targets = targets[:max_pages]

        synced_slugs: list[str] = []
        total_resources = 0
        total_chunks = 0
        errors: list[str] = []

        for slug in targets:
            try:
                doc, resp = self.sync_category(slug, force_refresh=force_refresh)
                synced_slugs.append(doc.doc_id)
                total_resources += doc.resource_count
                total_chunks += resp.indexed_count
            except Exception as e:
                logger.error(f"WebRAGIndexer: failed to sync category '{slug}': {e}")
                errors.append(f"{slug}: {e}")

        total_ms = (time.perf_counter() - t0) * 1000
        status = "completed" if not errors else ("partial" if synced_slugs else "failed")
        error_msg = "; ".join(errors) if errors else None

        return WebSyncResponse(
            synced_pages=synced_slugs,
            total_pages=len(synced_slugs),
            total_resources=total_resources,
            total_chunks=total_chunks,
            duration_ms=round(total_ms, 2),
            status=status,
            error=error_msg,
        )

    def list_sources(self) -> list[WebSourceItem]:
        """Lists all synchronized web source documents from the local metadata store."""
        sources: list[WebSourceItem] = []
        if not self.web_docs_dir.exists():
            return sources

        for f in sorted(self.web_docs_dir.glob("web_wiki_index_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                doc = WebPageDocument.model_validate(data)
                sources.append(
                    WebSourceItem(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        category=doc.category,
                        url=doc.url,
                        resources_count=doc.resource_count,
                        chunks_count=doc.blocks_count,
                        last_synced=doc.last_synced,
                    )
                )
            except Exception as e:
                logger.warning(f"Could not load web source file {f.name}: {e}")

        return sources

    def get_source(self, doc_id: str) -> WebPageDocument | None:
        """Retrieves complete metadata for an indexed web source."""
        clean_id = Path(doc_id).stem
        path = self.web_docs_dir / f"{clean_id}.json"
        if not path.exists():
            # Try appending web_wiki_index prefix if omitted
            path = self.web_docs_dir / f"web_wiki_index_{clean_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WebPageDocument.model_validate(data)
        except Exception:
            return None

    def _write_markdown_mirror(self, doc: WebPageDocument, blocks: list[Block]) -> Path:
        """Writes a clean markdown document to data/web_documents/ for review and document listing."""
        md_file = self.web_docs_dir / f"{doc.doc_id}.md"
        lines: list[str] = [
            f"# {doc.title}",
            "",
            f"**Source URL**: [{doc.url}]({doc.url})",
            f"**Category**: `{doc.category}`",
            f"**Total Resources**: {doc.resource_count}",
            f"**Last Synced**: {doc.last_synced}",
            "",
            "---",
            "",
        ]
        for b in blocks:
            if b.type.value == "heading":
                hashes = "#" * min(b.level or 2, 6)
                lines.append(f"\n{hashes} {b.text}\n")
            else:
                lines.append(f"{b.text}\n")

        md_file.write_text("\n".join(lines), encoding="utf-8")
        return md_file
