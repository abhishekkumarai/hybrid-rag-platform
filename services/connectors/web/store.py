"""Connector state in Redis (with an in-memory fallback, like projects): connectors, their pages, the
last sync report, a doc_id -> page index for the document library, and per-connector sync locks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from contracts.connector import ConnectorPage, SyncReport, WebConnector
from services.common.logger import get_logger

logger = get_logger("connectors.web.store")

_CONNECTORS = "rag:connectors"
_DOCS = "rag:connector_docs"


def _pages_key(cid: str) -> str:
    return f"rag:connector_pages:{cid}"


def _report_key(cid: str) -> str:
    return f"rag:connector_report:{cid}"


def _lock_key(cid: str) -> str:
    return f"rag:connector_lock:{cid}"


class ConnectorStore:
    def __init__(self, redis_client: Callable[[], Any]):
        self._redis = redis_client
        self._connectors: dict[str, WebConnector] = {}
        self._pages: dict[str, dict[str, ConnectorPage]] = {}
        self._reports: dict[str, SyncReport] = {}
        self._docs: dict[str, dict] = {}
        self._locks: set[str] = set()
        self._mu = threading.Lock()

    def _client(self):
        client = self._redis()
        return client

    # ---------------------------------------------------------------- connectors

    def save(self, connector: WebConnector) -> WebConnector:
        client = self._client()
        if client is not None:
            try:
                client.hset(_CONNECTORS, connector.id, connector.model_dump_json())
                return connector
            except Exception as exc:
                logger.error(f"Saving connector {connector.id} failed: {exc}")
        self._connectors[connector.id] = connector
        return connector

    def get(self, cid: str) -> WebConnector | None:
        client = self._client()
        if client is not None:
            try:
                raw = client.hget(_CONNECTORS, cid)
                return WebConnector.model_validate_json(raw) if raw else None
            except Exception as exc:
                logger.error(f"Reading connector {cid} failed: {exc}")
        return self._connectors.get(cid)

    def list(self) -> list[WebConnector]:
        client = self._client()
        if client is not None:
            try:
                return [WebConnector.model_validate_json(v) for v in client.hgetall(_CONNECTORS).values()]
            except Exception as exc:
                logger.error(f"Listing connectors failed: {exc}")
        return list(self._connectors.values())

    def delete(self, cid: str) -> None:
        client = self._client()
        if client is not None:
            try:
                client.hdel(_CONNECTORS, cid)
                client.delete(_pages_key(cid), _report_key(cid), _lock_key(cid))
                return
            except Exception as exc:
                logger.error(f"Deleting connector {cid} failed: {exc}")
        self._connectors.pop(cid, None)
        self._pages.pop(cid, None)
        self._reports.pop(cid, None)

    # ---------------------------------------------------------------- pages

    def pages(self, cid: str) -> dict[str, ConnectorPage]:
        client = self._client()
        if client is not None:
            try:
                return {u: ConnectorPage.model_validate_json(v) for u, v in client.hgetall(_pages_key(cid)).items()}
            except Exception as exc:
                logger.error(f"Reading pages of {cid} failed: {exc}")
        return dict(self._pages.get(cid, {}))

    def replace_pages(self, cid: str, pages: dict[str, ConnectorPage]) -> None:
        client = self._client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.delete(_pages_key(cid))
                if pages:
                    pipe.hset(_pages_key(cid), mapping={u: p.model_dump_json() for u, p in pages.items()})
                pipe.execute()
                return
            except Exception as exc:
                logger.error(f"Saving pages of {cid} failed: {exc}")
        self._pages[cid] = dict(pages)

    # ---------------------------------------------------------------- reports

    def save_report(self, report: SyncReport) -> None:
        client = self._client()
        if client is not None:
            try:
                client.set(_report_key(report.connector_id), report.model_dump_json())
                return
            except Exception as exc:
                logger.error(f"Saving report failed: {exc}")
        self._reports[report.connector_id] = report

    def report(self, cid: str) -> SyncReport | None:
        client = self._client()
        if client is not None:
            try:
                raw = client.get(_report_key(cid))
                return SyncReport.model_validate_json(raw) if raw else None
            except Exception as exc:
                logger.error(f"Reading report failed: {exc}")
        return self._reports.get(cid)

    # ---------------------------------------------------------------- doc index (for the library)

    def index_doc(self, doc_id: str, connector_id: str, url: str, title: str) -> None:
        import json

        entry = {"connector_id": connector_id, "url": url, "title": title}
        client = self._client()
        if client is not None:
            try:
                client.hset(_DOCS, doc_id, json.dumps(entry))
                return
            except Exception as exc:
                logger.error(f"Indexing doc {doc_id} failed: {exc}")
        self._docs[doc_id] = entry

    def unindex_doc(self, doc_id: str) -> None:
        client = self._client()
        if client is not None:
            try:
                client.hdel(_DOCS, doc_id)
                return
            except Exception as exc:
                logger.error(f"Unindexing doc {doc_id} failed: {exc}")
        self._docs.pop(doc_id, None)

    def doc_info(self, doc_ids: set[str]) -> dict[str, dict]:
        import json

        if not doc_ids:
            return {}
        client = self._client()
        if client is not None:
            try:
                ids = list(doc_ids)
                values = client.hmget(_DOCS, ids)
                return {d: json.loads(v) for d, v in zip(ids, values, strict=True) if v}
            except Exception as exc:
                logger.error(f"Reading doc index failed: {exc}")
        return {d: self._docs[d] for d in doc_ids if d in self._docs}

    # ---------------------------------------------------------------- locks

    def acquire(self, cid: str, ttl_s: int = 3600) -> bool:
        """One sync per connector at a time, across threads and gateway processes."""
        client = self._client()
        if client is not None:
            try:
                return bool(client.set(_lock_key(cid), "1", nx=True, ex=ttl_s))
            except Exception as exc:
                logger.error(f"Lock for {cid} failed: {exc}")
        with self._mu:
            if cid in self._locks:
                return False
            self._locks.add(cid)
            return True

    def release(self, cid: str) -> None:
        client = self._client()
        if client is not None:
            try:
                client.delete(_lock_key(cid))
                return
            except Exception as exc:
                logger.error(f"Unlock for {cid} failed: {exc}")
        with self._mu:
            self._locks.discard(cid)
