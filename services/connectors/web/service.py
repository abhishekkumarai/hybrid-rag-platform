"""Sync a website connector into the index (IRA-57).

A sync crawls the site, turns each page into blocks, and indexes only what changed (content hash). A page
whose content changed gets a new content-addressed doc_id, so its previous document is retired; pages
that disappeared from the site are retired too, but only after a *complete* crawl (one cut short by the
page cap can't tell "gone" from "not reached"). A retired document leaves the owner's library and, when
no one else owns identical content, the dense and sparse indexes. A linked project's sources follow.

Runs in the gateway process on purpose: it must write through the gateway's own IndexingService, since
the BM25 index and graph are in-process state (CLAUDE.md "Store ownership").
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from contracts.connector import ConnectorPage, CrawlScope, SyncReport, WebConnector
from contracts.document import Block, BlockType, IngestRequest
from contracts.identity import OwnedDocument
from contracts.session import UpdateSessionRequest
from services.common.config import ConnectorsConfig
from services.common.logger import get_logger
from services.connectors.web.crawler import CrawledPage, Crawler, CrawlSettings
from services.connectors.web.extractor import doc_id_for, finalize_blocks
from services.connectors.web.store import ConnectorStore

logger = get_logger("connectors.web.service")

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "connectors"
_INTERVALS = {"daily": 86_400, "weekly": 7 * 86_400}
_REPORT_FIELD = {"indexed": "indexed", "unchanged": "unchanged", "needs_js": "needs_js", "error": "errors"}


def next_sync_time(connector: WebConnector, now: float) -> float | None:
    interval = _INTERVALS.get(connector.schedule)
    return now + interval if interval else None


def blocks_to_markdown(title: str, url: str, blocks: list[Block]) -> str:
    out = [f"# {title}", "", f"Source: {url}", ""]
    for b in blocks:
        if b.type == BlockType.HEADING:
            out += [f"{'#' * min((b.level or 1) + 1, 6)} {b.text}", ""]
        elif b.type == BlockType.CODE:
            out += ["```", b.text, "```", ""]
        else:
            out += [b.text, ""]
    return "\n".join(out)


class WebConnectorService:
    def __init__(
        self,
        store: ConnectorStore,
        indexing: Callable[[], Any],
        identity: Callable[[], Any],
        sessions: Any,
        ingestion: Callable[[], Any],
        config: ConnectorsConfig,
        crawler_factory: Callable[..., Crawler] = Crawler,
        data_dir: Path = DATA_DIR,
    ):
        self.store = store
        self._indexing = indexing
        self._identity = identity
        self.sessions = sessions
        self._ingestion = ingestion
        self.config = config
        self.crawler_factory = crawler_factory
        self.data_dir = data_dir

    # ------------------------------------------------------------------ helpers

    def clamp_scope(self, scope: CrawlScope) -> CrawlScope:
        return scope.model_copy(update={"max_pages": min(scope.max_pages, self.config.max_pages_cap)})

    def _settings(self) -> CrawlSettings:
        c = self.config
        return CrawlSettings(
            user_agent=c.user_agent, timeout_s=c.request_timeout_s, max_page_bytes=c.max_page_bytes,
            delay_s=c.crawl_delay_s, browser_timeout_s=c.browser_timeout_s, min_words=c.min_words,
        )

    def _owner_dir(self, owner_id: str) -> Path:
        d = self.data_dir / re.sub(r"[^A-Za-z0-9_-]", "_", owner_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _own(self, connector: WebConnector, doc_id: str, title: str, path: Path, url: str) -> None:
        self._identity().add_document(OwnedDocument(user_id=connector.owner_id, doc_id=doc_id, filename=title or url, path=str(path)))
        self.store.index_doc(doc_id, connector.id, url, title)

    def retire(self, connector: WebConnector, doc_id: str) -> None:
        """Removes one superseded/vanished page's document from the owner and, if unshared, the index."""
        identity = self._identity()
        identity.remove_document(connector.owner_id, doc_id)
        self.store.unindex_doc(doc_id)
        if identity.document_owner_count(doc_id) == 0:
            self._indexing().remove_document(doc_id)

    # ------------------------------------------------------------------ one page

    def _index_html(self, connector: WebConnector, crawled: CrawledPage, old: ConnectorPage | None) -> ConnectorPage:
        page = crawled.page
        assert page is not None
        base = ConnectorPage(url=crawled.url, title=page.title, depth=crawled.depth, rendered_with=crawled.rendered_with,
                             words=page.words, blocks=len(page.blocks), content_hash=page.content_hash)
        if crawled.needs_js:
            return base.model_copy(update={"status": "needs_js", "error": crawled.error or "Too little text without JavaScript"})
        if page.words < self.config.min_words:
            return base.model_copy(update={"status": "skipped", "error": "Too little readable text"})
        doc_id = doc_id_for(crawled.url, page.content_hash)
        path = self._owner_dir(connector.owner_id) / f"{doc_id}.md"
        if old and old.doc_id == doc_id and old.status in ("indexed", "unchanged"):
            if not path.exists():
                path.write_text(blocks_to_markdown(page.title, crawled.url, page.blocks), encoding="utf-8")
            self._own(connector, doc_id, page.title, path, crawled.url)
            return base.model_copy(update={"doc_id": doc_id, "status": "unchanged", "changed_at": old.changed_at})
        blocks = finalize_blocks(page, doc_id)
        path.write_text(blocks_to_markdown(page.title, crawled.url, blocks), encoding="utf-8")
        self._indexing().chunk_and_index(doc_id, blocks)
        self._own(connector, doc_id, page.title, path, crawled.url)
        return base.model_copy(update={"doc_id": doc_id, "status": "indexed", "changed_at": time.time()})

    def _index_pdf(self, connector: WebConnector, crawled: CrawledPage, old: ConnectorPage | None) -> ConnectorPage:
        import hashlib

        content_hash = hashlib.sha256(crawled.pdf_bytes or b"").hexdigest()
        name = doc_id_for(crawled.url, "x").rsplit("_", 1)[0]
        path = self._owner_dir(connector.owner_id) / f"{name}.pdf"
        base = ConnectorPage(url=crawled.url, title=Path(crawled.url).name or crawled.url, depth=crawled.depth,
                             rendered_with="pdf", content_hash=content_hash)
        if old and old.content_hash == content_hash and old.doc_id and old.status in ("indexed", "unchanged"):
            self._own(connector, old.doc_id, base.title, path, crawled.url)
            return base.model_copy(update={"doc_id": old.doc_id, "status": "unchanged", "changed_at": old.changed_at,
                                           "blocks": old.blocks, "words": old.words})
        path.write_bytes(crawled.pdf_bytes or b"")
        res = self._ingestion().parse(IngestRequest(file_path=str(path)))
        if res.error or not res.blocks:
            return base.model_copy(update={"status": "error", "error": res.error or "No text in PDF"})
        blocks = [b.model_copy(update={"meta": {**b.meta, "source": "web_connector", "url": crawled.url,
                                                "section_url": f"{crawled.url}#page={b.page}"}}) for b in res.blocks]
        self._indexing().chunk_and_index(res.doc_id, blocks)
        self._own(connector, res.doc_id, base.title, path, crawled.url)
        words = sum(len(b.text.split()) for b in blocks)
        return base.model_copy(update={"doc_id": res.doc_id, "status": "indexed", "changed_at": time.time(),
                                       "blocks": len(blocks), "words": words})

    # ------------------------------------------------------------------ sync

    def sync(self, connector_id: str) -> SyncReport | None:
        connector = self.store.get(connector_id)
        if connector is None:
            return None
        if not self.store.acquire(connector_id):
            logger.info(f"Connector {connector_id} is already syncing; skipped")
            return None
        started = time.time()
        report = SyncReport(connector_id=connector_id, started_at=started, finished_at=started)
        try:
            connector = self.store.save(connector.model_copy(update={"status": "running", "last_error": None}))
            old_pages = self.store.pages(connector_id)
            crawler = self.crawler_factory(connector.start_url, self.clamp_scope(connector.scope), connector.render, self._settings())
            new_pages: dict[str, ConnectorPage] = {}
            retired: set[str] = set()

            for crawled in crawler.run():
                report.pages_seen += 1
                old = old_pages.get(crawled.url)
                try:
                    if crawled.kind == "html" and crawled.page is not None:
                        page = self._index_html(connector, crawled, old)
                    elif crawled.kind == "pdf":
                        page = self._index_pdf(connector, crawled, old)
                    elif crawled.kind == "html":  # needs JS and couldn't render
                        page = ConnectorPage(url=crawled.url, depth=crawled.depth, status="needs_js", error=crawled.error)
                    else:
                        page = ConnectorPage(url=crawled.url, depth=crawled.depth,
                                             status="error" if crawled.kind == "error" else "skipped", error=crawled.error)
                except Exception as exc:  # one bad page must not sink the whole sync
                    logger.warning(f"Connector {connector_id}: page {crawled.url} failed: {exc}")
                    page = ConnectorPage(url=crawled.url, depth=crawled.depth, status="error", error=str(exc)[:300])
                counter = _REPORT_FIELD.get(page.status, "skipped")
                setattr(report, counter, getattr(report, counter) + 1)
                if old and old.doc_id and old.doc_id != page.doc_id:
                    retired.add(old.doc_id)  # content changed (or page now fails): previous version goes
                new_pages[crawled.url] = page

            if crawler.complete:
                for url, old in old_pages.items():
                    if url not in new_pages and old.doc_id:
                        retired.add(old.doc_id)
                        report.removed += 1
            else:  # partial crawl: keep pages we didn't reach this time
                for url, old in old_pages.items():
                    new_pages.setdefault(url, old)

            current = {p.doc_id for p in new_pages.values() if p.doc_id and p.status in ("indexed", "unchanged")}
            retired -= current
            for doc_id in retired:
                self.retire(connector, doc_id)
            self.store.replace_pages(connector_id, new_pages)
            self._sync_project(connector, current, retired)

            finished = time.time()
            report.finished_at = finished
            report.status = "error" if not current and report.errors else ("partial" if report.errors or report.needs_js else "ok")
            self.store.save(connector.model_copy(update={
                "status": report.status, "last_sync_at": finished, "last_sync_duration_s": round(finished - started, 1),
                "next_sync_at": next_sync_time(connector, finished), "page_count": len(current),
                "last_error": None if report.status != "error" else "No pages could be indexed",
            }))
            logger.info(f"Connector {connector_id} synced: {report.model_dump(exclude={'connector_id'})}")
        except Exception as exc:
            logger.error(f"Connector {connector_id} sync failed: {exc}")
            report.status = "error"
            report.finished_at = time.time()
            fresh = self.store.get(connector_id) or connector
            self.store.save(fresh.model_copy(update={
                "status": "error", "last_error": str(exc)[:300], "last_sync_at": report.finished_at,
                "next_sync_at": next_sync_time(fresh, report.finished_at),
            }))
        finally:
            self.store.save_report(report)
            self.store.release(connector_id)
        return report

    def _sync_project(self, connector: WebConnector, current: set[str], retired: set[str]) -> None:
        if not connector.project_id:
            return
        session, _ = self.sessions.get_session(connector.project_id)
        if session is None:
            return
        files = [f for f in session.files if f not in retired]
        files += [d for d in sorted(current) if d not in files]
        if files != session.files:
            self.sessions.update_session(connector.project_id, UpdateSessionRequest(files=files))

    def detach_from_project(self, connector: WebConnector) -> None:
        if not connector.project_id:
            return
        session, _ = self.sessions.get_session(connector.project_id)
        if session is None:
            return
        mine = {p.doc_id for p in self.store.pages(connector.id).values() if p.doc_id}
        files = [f for f in session.files if f not in mine]
        if files != session.files:
            self.sessions.update_session(connector.project_id, UpdateSessionRequest(files=files))

    def delete(self, connector: WebConnector) -> None:
        """Removes the connector, its pages' documents (from the owner and, if unshared, the index) and
        the linked project's references to them."""
        self.detach_from_project(connector)
        for page in self.store.pages(connector.id).values():
            if page.doc_id:
                self.retire(connector, page.doc_id)
        self.store.delete(connector.id)

    def due(self, now: float | None = None) -> list[WebConnector]:
        now = now or time.time()
        return [c for c in self.store.list()
                if c.schedule != "manual" and c.status not in ("running", "queued") and (c.next_sync_at or 0) <= now]
