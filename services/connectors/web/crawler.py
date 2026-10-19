"""Polite, scoped website crawl (IRA-57).

Breadth-first from the start URL (plus sitemap.xml entries), staying on the site and under the
connector's path prefix, honoring robots.txt and its crawl-delay, de-duplicating by normalized URL,
canonical link and content hash. Every fetch goes through the SSRF-guarded fetcher.
"""

from __future__ import annotations

import re
import time
import urllib.robotparser
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from contracts.connector import CrawlScope, RenderMode
from services.common.logger import get_logger
from services.connectors.web import renderer
from services.connectors.web.extractor import ExtractedPage, extract, normalize_url
from services.ingestion.url_source import UrlSourceError, fetch_public_url

logger = get_logger("connectors.web.crawler")

_SKIP_EXT = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|ico|css|js|mjs|json|xml|rss|atom|zip|gz|tgz|rar|7z|exe|dmg|msi|mp[34]|"
    r"mov|avi|webm|wav|ogg|woff2?|ttf|eot|docx?|xlsx?|pptx?|csv)$",
    re.I,
)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


@dataclass
class CrawlSettings:
    user_agent: str
    timeout_s: float
    max_page_bytes: int
    delay_s: float
    browser_timeout_s: float
    min_words: int


@dataclass
class CrawledPage:
    url: str
    depth: int
    kind: Literal["html", "pdf", "error", "skipped"]
    page: ExtractedPage | None = None
    pdf_bytes: bytes | None = None
    rendered_with: Literal["static", "browser", "pdf"] = "static"
    needs_js: bool = False
    error: str | None = None


class Crawler:
    def __init__(
        self,
        start_url: str,
        scope: CrawlScope,
        render: RenderMode,
        settings: CrawlSettings,
        fetch: Callable[..., object] = fetch_public_url,
        render_page: Callable[..., tuple[str, str]] | None = None,
    ):
        self.start = normalize_url(start_url)
        p = urlparse(self.start)
        self.scheme, self.host = p.scheme, (p.hostname or "")
        self.scope = scope
        self.render_mode = render
        self.settings = settings
        self._fetch = fetch
        self._render = render_page if render_page is not None else (renderer.render if renderer.browser_available() else None)
        self.robots = urllib.robotparser.RobotFileParser()
        self.robots_loaded = False
        self.delay = settings.delay_s
        self.complete = False  # True once the frontier is exhausted (not cut short by max_pages)
        prefix = scope.path_prefix or "/"
        self.prefix = prefix if prefix.startswith("/") else f"/{prefix}"

    # ------------------------------------------------------------------ scope

    def in_scope(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        same_site = host == self.host or (self.scope.include_subdomains and host.endswith("." + self.host.split(":")[0].removeprefix("www.")))
        if p.scheme not in ("http", "https") or not same_site:
            return False
        if not (p.path or "/").startswith(self.prefix.rstrip("/") or "/"):
            return False
        if _SKIP_EXT.search(p.path or ""):
            return False
        return not any(x and x in url for x in self.scope.exclude_patterns)

    # ------------------------------------------------------------------ fetch helpers

    def _get(self, url: str, max_bytes: int | None = None):
        return self._fetch(url, max_bytes=max_bytes or self.settings.max_page_bytes, timeout_s=self.settings.timeout_s, max_redirects=5)

    def _load_robots(self) -> list[str]:
        sitemaps: list[str] = []
        try:
            res = self._get(f"{self.scheme}://{self.host}/robots.txt", max_bytes=512_000)
            lines = res.body.decode("utf-8", errors="replace").splitlines()
            self.robots.parse(lines)
            self.robots_loaded = True
            delay = self.robots.crawl_delay(self.settings.user_agent)
            if delay:
                self.delay = max(self.delay, min(float(delay), 10.0))
            sitemaps = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
        except (UrlSourceError, Exception) as exc:  # no robots.txt = everything allowed
            logger.debug(f"robots.txt unavailable for {self.host}: {exc}")
        return sitemaps

    def allowed_by_robots(self, url: str) -> bool:
        return not self.robots_loaded or self.robots.can_fetch(self.settings.user_agent, url)

    def _sitemap_urls(self, extra: list[str]) -> list[str]:
        found: list[str] = []
        queue = deque(extra or [f"{self.scheme}://{self.host}/sitemap.xml"])
        seen: set[str] = set()
        while queue and len(seen) < 10 and len(found) < self.scope.max_pages * 3:
            sm = queue.popleft()
            if sm in seen:
                continue
            seen.add(sm)
            try:
                body = self._get(sm, max_bytes=5_000_000).body.decode("utf-8", errors="replace")
            except Exception:
                continue
            is_index = "<sitemapindex" in body[:2000].lower()
            for loc in _LOC.findall(body):
                if is_index:
                    queue.append(loc)  # a sitemap index lists child sitemaps, not pages
                else:
                    found.append(normalize_url(loc))
        return found

    def _fetch_page(self, url: str, depth: int) -> CrawledPage:
        want_browser = self.render_mode == "browser"
        html, final_url = None, url
        if not want_browser:
            res = self._get(url)
            if res.content_type == "application/pdf" or res.body[:4] == b"%PDF":
                return CrawledPage(url=normalize_url(res.url), depth=depth, kind="pdf", pdf_bytes=res.body, rendered_with="pdf")
            if res.content_type not in ("text/html", "application/xhtml+xml", ""):
                return CrawledPage(url=url, depth=depth, kind="skipped", error=f"not a web page ({res.content_type})")
            html, final_url = res.body.decode("utf-8", errors="replace"), res.url
            page = extract(html, normalize_url(final_url))
            if not page.needs_js or self.render_mode == "static":
                return CrawledPage(url=page.url, depth=depth, kind="html", page=page, needs_js=page.needs_js and page.words < self.settings.min_words)
        if self._render is None:
            return CrawledPage(url=normalize_url(final_url), depth=depth, kind="html",
                               page=extract(html, normalize_url(final_url)) if html else None, needs_js=True,
                               error="This page needs JavaScript and no headless browser is installed")
        final_url, html = self._render(url, timeout_s=self.settings.browser_timeout_s, user_agent=self.settings.user_agent)
        page = extract(html, normalize_url(final_url))
        return CrawledPage(url=page.url, depth=depth, kind="html", page=page, rendered_with="browser",
                           needs_js=page.words < self.settings.min_words)

    # ------------------------------------------------------------------ crawl

    def run(self) -> Iterator[CrawledPage]:
        sitemaps = self._load_robots()
        frontier: deque[tuple[str, int]] = deque([(self.start, 0)])
        queued = {self.start}
        if self.scope.use_sitemap:
            for u in self._sitemap_urls(sitemaps):
                if u not in queued and self.in_scope(u):
                    queued.add(u)
                    frontier.append((u, 1))
        visited = 0
        seen_content: set[str] = set()
        last = 0.0
        while frontier:
            if visited >= self.scope.max_pages:
                return  # budget exhausted: the crawl is not complete
            url, depth = frontier.popleft()
            if not self.allowed_by_robots(url):
                yield CrawledPage(url=url, depth=depth, kind="skipped", error="disallowed by robots.txt")
                continue
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.monotonic()
            visited += 1
            try:
                result = self._fetch_page(url, depth)
            except (UrlSourceError, Exception) as exc:
                yield CrawledPage(url=url, depth=depth, kind="error", error=str(exc)[:300])
                continue
            page = result.page
            if page is not None:
                if page.canonical and page.canonical != page.url and page.canonical in queued and self.in_scope(page.canonical):
                    yield CrawledPage(url=url, depth=depth, kind="skipped", error=f"duplicate of {page.canonical}")
                    continue
                if page.content_hash in seen_content and page.words:
                    yield CrawledPage(url=url, depth=depth, kind="skipped", error="same content as another page")
                    continue
                seen_content.add(page.content_hash)
                if depth < self.scope.max_depth:
                    for link in page.links:
                        if link not in queued and self.in_scope(link):
                            queued.add(link)
                            frontier.append((link, depth + 1))
            yield result
        self.complete = True
