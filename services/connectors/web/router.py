"""HTTP API for website connectors (IRA-57), mounted by the gateway with `build_router`.

Connectors are private to their owner: anyone else gets a 404, like projects. Syncs run in the
background (Starlette runs sync callables in its threadpool), and the scheduler loop starts the
daily/weekly ones that are due.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from contracts.connector import (
    ConnectorDetailResponse,
    ConnectorListResponse,
    CrawlScope,
    CreateConnectorRequest,
    UpdateConnectorRequest,
    WebConnector,
)
from contracts.identity import User
from services.common.logger import get_logger
from services.connectors.web.extractor import normalize_url
from services.connectors.web.service import WebConnectorService, next_sync_time
from services.ingestion.url_source import UrlSourceError, check_public_url

logger = get_logger("connectors.web.router")

_PAGE_ORDER = {"error": 0, "needs_js": 1, "indexed": 2, "unchanged": 3, "skipped": 4, "removed": 5}


@dataclass
class ConnectorDeps:
    service: Callable[[], WebConnectorService]
    user_workspaces: Callable[[User], set[str]]
    project_visible: Callable[[str, User], bool]


def build_router(current_user: Callable[..., User], deps: ConnectorDeps) -> APIRouter:
    router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])

    def owned(connector_id: str, user: User = Depends(current_user)) -> WebConnector:
        connector = deps.service().store.get(connector_id)
        if connector is None or connector.owner_id != user.id:
            raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")
        return connector

    def queue_sync(connector: WebConnector, background: BackgroundTasks) -> WebConnector:
        service = deps.service()
        queued = service.store.save(connector.model_copy(update={"status": "queued"}))
        background.add_task(service.sync, connector.id)
        return queued

    def check_links(user: User, workspace_id: str | None, project_id: str | None) -> None:
        if workspace_id and workspace_id not in deps.user_workspaces(user):
            raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found")
        if project_id and not deps.project_visible(project_id, user):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    @router.get("", response_model=ConnectorListResponse)
    def list_connectors(workspace_id: str | None = Query(default=None), user: User = Depends(current_user)):
        mine = [c for c in deps.service().store.list() if c.owner_id == user.id]
        if workspace_id:
            mine = [c for c in mine if c.workspace_id == workspace_id]
        return ConnectorListResponse(connectors=sorted(mine, key=lambda c: c.created_at, reverse=True))

    @router.post("", response_model=WebConnector)
    def create_connector(req: CreateConnectorRequest, background: BackgroundTasks, user: User = Depends(current_user)):
        service = deps.service()
        if not service.config.enabled:
            raise HTTPException(status_code=403, detail="Website connectors are disabled on this server")
        url = req.start_url.strip()
        if "://" not in url:
            url = f"https://{url}"
        try:
            check_public_url(url)
        except UrlSourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        check_links(user, req.workspace_id, req.project_id)
        url = normalize_url(url)
        scope = req.scope or CrawlScope()
        if scope.path_prefix in ("", "/") and urlparse(url).path not in ("", "/"):
            # Default to the section the user pointed at, e.g. https://docs.x.com/guide/ -> /guide.
            scope = scope.model_copy(update={"path_prefix": urlparse(url).path.rsplit("/", 1)[0] or "/"})
        connector = WebConnector(
            name=(req.name or "").strip() or (urlparse(url).hostname or url),
            start_url=url, owner_id=user.id, workspace_id=req.workspace_id, project_id=req.project_id,
            scope=service.clamp_scope(scope), render=req.render, schedule=req.schedule,
        )
        connector = connector.model_copy(update={"next_sync_at": next_sync_time(connector, time.time())})
        service.store.save(connector)
        logger.info(f"Connector {connector.id} created for {url} by {user.id}")
        return queue_sync(connector, background) if req.sync_now else connector

    @router.get("/{connector_id}", response_model=ConnectorDetailResponse)
    def get_connector(connector: WebConnector = Depends(owned)):
        store = deps.service().store
        pages = sorted(store.pages(connector.id).values(), key=lambda p: (_PAGE_ORDER.get(p.status, 9), p.url))
        return ConnectorDetailResponse(connector=connector, pages=pages, last_report=store.report(connector.id))

    @router.patch("/{connector_id}", response_model=WebConnector)
    def update_connector(req: UpdateConnectorRequest, connector: WebConnector = Depends(owned), user: User = Depends(current_user)):
        service = deps.service()
        changes = req.model_dump(exclude_unset=True)
        if "project_id" in changes:
            check_links(user, None, changes["project_id"])
            if changes["project_id"] != connector.project_id:
                service.detach_from_project(connector)
        if "scope" in changes and req.scope is not None:
            changes["scope"] = service.clamp_scope(req.scope)
        if "name" in changes:
            changes["name"] = (req.name or "").strip() or connector.name
        updated = connector.model_copy(update=changes)
        if "schedule" in changes:
            updated = updated.model_copy(update={"next_sync_at": next_sync_time(updated, updated.last_sync_at or time.time())})
        service.store.save(updated)
        if "project_id" in changes and updated.project_id:
            current = {p.doc_id for p in service.store.pages(updated.id).values()
                       if p.doc_id and p.status in ("indexed", "unchanged")}
            service._sync_project(updated, current, set())
        return updated

    @router.post("/{connector_id}/sync", response_model=WebConnector)
    def sync_connector(background: BackgroundTasks, connector: WebConnector = Depends(owned)):
        if connector.status in ("queued", "running"):
            raise HTTPException(status_code=409, detail="A sync is already in progress")
        return queue_sync(connector, background)

    @router.delete("/{connector_id}")
    def delete_connector(connector: WebConnector = Depends(owned)) -> dict[str, bool]:
        deps.service().delete(connector)
        return {"deleted": True}

    return router


async def scheduler_loop(service: Callable[[], WebConnectorService], interval_s: float) -> None:
    """Starts due daily/weekly syncs. The store's lock keeps one sync per connector across processes."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            svc = service()
            for connector in svc.due():
                svc.store.save(connector.model_copy(update={"status": "queued"}))
                await asyncio.to_thread(svc.sync, connector.id)
        except Exception as exc:
            logger.warning(f"Connector scheduler tick failed: {exc}")
