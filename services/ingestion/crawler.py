"""Crawl4AI wrapper for "Add source -> Web" (IRA-68).

Pages are rendered in headless Chromium (so JS-built content is captured) and kept as markdown; an
optional breadth-first crawl follows same-site links. This is the only module that imports crawl4ai,
and it imports it lazily so a gateway without the `crawl` extra still starts.

Security: a browser makes requests the old `requests` fetch never did — redirects, scripts, iframes,
XHR, images. Every one of them goes through `url_source.check_public_url`, so a public page cannot
pull the crawler into the internal network: the start URL is checked, every discovered link is
filtered before it is queued, and a Playwright route handler vets each network request the page makes.
"""

from __future__ import annotations

import asyncio
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from services.common.config import load_config
from services.common.logger import get_logger
from services.ingestion.url_source import UrlSourceError, check_public_url

logger = get_logger("ingestion.crawler")

_NON_NETWORK_SCHEMES = {"data", "blob", "about"}


class CrawlError(Exception):
    """The page(s) could not be crawled; the message is safe to show the user."""


class CrawlUnavailable(CrawlError):
    """Crawl4AI or its browser can't run in this environment; callers fall back to the PDF fetch."""


@dataclass
class CrawledPage:
    url: str
    title: str
    markdown: str


def available() -> bool:
    return importlib.util.find_spec("crawl4ai") is not None


class _HostGuard:
    """`check_public_url` with a per-crawl cache, since a page makes many requests to few hosts."""

    def __init__(self) -> None:
        self._allow_private = load_config().ingestion.crawl_allow_private
        self._seen: dict[tuple[str, str], bool] = {}

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        if parts.scheme in _NON_NETWORK_SCHEMES:
            return True
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        key = (parts.scheme, parts.netloc)
        if key not in self._seen:
            if self._allow_private:
                self._seen[key] = True
            else:
                try:
                    check_public_url(url)
                    self._seen[key] = True
                except UrlSourceError as exc:
                    logger.warning(f"Crawler blocked {parts.netloc}: {exc}")
                    self._seen[key] = False
        return self._seen[key]


async def _crawl(url: str, max_depth: int, max_pages: int, guard: _HostGuard) -> list[CrawledPage]:
    try:
        from crawl4ai import (
            AsyncWebCrawler,
            BFSDeepCrawlStrategy,
            BrowserConfig,
            CacheMode,
            CrawlerRunConfig,
            FilterChain,
        )
        from crawl4ai.deep_crawling import URLFilter
    except ImportError as exc:
        raise CrawlUnavailable("Crawl4AI is not installed") from exc

    cfg = load_config().ingestion

    class PublicOnly(URLFilter):
        """Drops a discovered link that points off the public internet before it is ever queued."""

        def __init__(self) -> None:
            super().__init__(name="PublicOnly")

        def apply(self, url: str) -> bool:
            ok = guard.allowed(url)
            self._update_stats(ok)
            return ok

    async def vet_request(route) -> None:  # every request the page makes, navigations included
        target = route.request.url
        if await asyncio.to_thread(guard.allowed, target):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")

    async def on_page_context_created(page, context, **kwargs):
        await context.route("**/*", vet_request)
        return page

    deep = None
    if max_depth > 0:
        deep = BFSDeepCrawlStrategy(
            max_depth=max_depth,
            max_pages=max_pages,
            include_external=False,
            filter_chain=FilterChain([PublicOnly()]),
        )
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=int(cfg.crawl_page_timeout_s * 1000),
        wait_until="load",
        delay_before_return_html=0.5,  # let a script finish building the DOM after `load`
        deep_crawl_strategy=deep,
        stream=False,
        verbose=False,
    )
    browser_cfg = BrowserConfig(headless=True, verbose=False, extra_args=["--disable-dev-shm-usage"])

    crawler = AsyncWebCrawler(config=browser_cfg)
    try:
        await crawler.start()
    except Exception as exc:  # no browser binary, missing system libs, sandbox problems...
        raise CrawlUnavailable(f"headless browser failed to start: {exc}") from exc
    try:
        crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context_created)
        try:
            results = await crawler.arun(url, config=run_cfg)
        except Exception as exc:
            raise CrawlError(f"Could not crawl {url}: {str(exc)[:200]}") from exc
    finally:
        await crawler.close()

    pages: list[CrawledPage] = []
    last_error = ""
    for res in list(results):
        if not getattr(res, "success", False):
            last_error = (getattr(res, "error_message", "") or "")[:200]
            continue
        final_url = getattr(res, "redirected_url", None) or res.url
        if not guard.allowed(final_url):  # a redirect that ended somewhere private
            continue
        markdown = getattr(res.markdown, "raw_markdown", None) or str(res.markdown or "")
        markdown = markdown.strip()[: cfg.crawl_max_markdown_bytes]
        if not markdown:
            continue
        title = ((getattr(res, "metadata", None) or {}).get("title") or "").strip()
        pages.append(CrawledPage(url=final_url, title=title, markdown=markdown))
        if len(pages) >= max_pages:
            break
    if not pages:
        raise CrawlError(f"No readable content found at {url}" + (f" ({last_error})" if last_error else ""))
    return pages


def crawl(url: str, *, max_depth: int = 0, max_pages: int = 1) -> list[CrawledPage]:
    """Renders `url` (and, for max_depth > 0, same-site links up to max_pages) and returns markdown pages."""
    guard = _HostGuard()
    if not guard.allowed(url):
        raise CrawlError("That URL is not publicly reachable")
    if not available():
        raise CrawlUnavailable("Crawl4AI is not installed")
    cfg = load_config().ingestion
    budget = cfg.crawl_page_timeout_s * max(1, max_pages) + 60
    # Fresh thread: asyncio.run needs a thread with no running event loop, whoever calls us.
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, _crawl(url, max_depth, max_pages, guard))
        try:
            return future.result(timeout=budget)
        except TimeoutError as exc:
            raise CrawlError(f"Crawling {url} timed out") from exc
