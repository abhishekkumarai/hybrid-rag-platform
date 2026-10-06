"""Web document parser and crawler for wiki-index.pages.dev (IRA-25, IRA-26)."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import bs4
import requests

from contracts.document import Block, BlockType
from contracts.web import WebPageDocument, WebResourceLink
from services.common.config import load_config
from services.common.logger import get_logger

logger = get_logger("ingestion.web_parser")

# Anchored to the repo, not the cwd, so the cache and mirrors resolve wherever the gateway starts.
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BASE_URL = "https://wiki-index.pages.dev"

# Core wiki-index categories
DEFAULT_CATEGORIES: list[str] = [
    "ai",
    "developer-tools",
    "internet-tools",
    "video",
    "audio",
    "gaming",
    "reading",
    "downloading",
    "torrenting",
    "educational",
    "mobile",
    "linux-macos",
    "system-tools",
    "text-tools",
    "image-tools",
    "social-media-tools",
    "video-tools",
    "storage",
    "privacy",
    "misc",
    "beginners-guide",
]


def slugify(text: str) -> str:
    """Creates a normalized URL anchor slug from header text."""
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


class WikiIndexWebParser:
    """Fetches and parses wiki-index.pages.dev into structured blocks and resource links."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Path | str | None = None,
        timeout_seconds: float = 12.0,
        cache_ttl_s: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir or REPO_ROOT / "data" / "web_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_s = load_config().ingestion.web_cache_ttl_s if cache_ttl_s is None else cache_ttl_s

    def fetch_sitemap_slugs(self) -> list[str]:
        """Fetches sitemap.xml and returns all non-blog category slugs."""
        sitemap_url = f"{self.base_url}/sitemap.xml"
        slugs: list[str] = []
        try:
            resp = requests.get(sitemap_url, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//sm:loc", ns):
                    if not loc.text:
                        continue
                    path = urlparse(loc.text).path.strip("/")
                    if path and not path.startswith("blog"):
                        slugs.append(path)
        except Exception as e:
            logger.warning(f"Could not fetch sitemap from {sitemap_url} ({e}); falling back to default categories")

        if not slugs:
            slugs = list(DEFAULT_CATEGORIES)
        return sorted(list(dict.fromkeys(slugs)))

    def _cache_is_fresh(self, cache_file: Path) -> bool:
        if self.cache_ttl_s <= 0 or not cache_file.exists():
            return False
        return time.time() - cache_file.stat().st_mtime < self.cache_ttl_s

    def fetch_page_html(self, slug_or_url: str, force_refresh: bool = False) -> tuple[str, str, str]:
        """Fetches the HTML content for a category slug or URL, caching locally.

        Returns (slug, page_url, html_content).
        """
        if slug_or_url.startswith("http://") or slug_or_url.startswith("https://"):
            if urlparse(slug_or_url).netloc.lower() != urlparse(self.base_url).netloc.lower():
                raise ValueError(f"Refusing to fetch {slug_or_url}: not on {self.base_url}")
            page_url = slug_or_url
            slug = urlparse(slug_or_url).path.strip("/") or "index"
        else:
            slug = slug_or_url.strip("/")
            page_url = f"{self.base_url}/{slug}/" if slug else f"{self.base_url}/"

        safe_slug = re.sub(r"[^\w-]", "_", slug) or "index"
        cache_file = self.cache_dir / f"{safe_slug}.html"

        if not force_refresh and self._cache_is_fresh(cache_file):
            try:
                html = cache_file.read_text(encoding="utf-8")
                if html.strip():
                    return slug, page_url, html
            except Exception:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HybridRAG/1.0 (Web-Store-Crawler)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        resp = requests.get(page_url, headers=headers, timeout=self.timeout_seconds)
        if resp.status_code != 200:
            # Try without trailing slash if failed
            alt_url = page_url.rstrip("/")
            if alt_url != page_url:
                resp = requests.get(alt_url, headers=headers, timeout=self.timeout_seconds)
                if resp.status_code == 200:
                    page_url = alt_url

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch {page_url}: HTTP status {resp.status_code}")

        html = resp.text
        try:
            cache_file.write_text(html, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not write cache file {cache_file}: {e}")

        return slug, page_url, html

    def parse_page(self, slug_or_url: str, force_refresh: bool = False) -> tuple[WebPageDocument, list[Block]]:
        """Parses a wiki-index category page into a WebPageDocument and list of Block items."""
        slug, page_url, html = self.fetch_page_html(slug_or_url, force_refresh=force_refresh)
        soup = bs4.BeautifulSoup(html, "html.parser")

        # Document ID normalization
        clean_slug = re.sub(r"[^\w-]", "_", slug) or "index"
        doc_id = f"web_wiki_index_{clean_slug}"

        # Extract title
        title = ""
        title_el = soup.find("title")
        if title_el and title_el.get_text(strip=True):
            title = title_el.get_text(strip=True)
            # Retype format is often "Title | Wiki Index"
            if "|" in title:
                title = title.split("|")[0].strip()

        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else clean_slug.replace("-", " ").title()

        # Locate content container
        content_div = soup.find("div", id="retype-content") or soup.find("main") or soup.body
        if not content_div:
            content_div = soup

        blocks: list[Block] = []
        resources: list[WebResourceLink] = []

        heading_stack: list[str] = [title]
        current_section = title
        current_anchor = slugify(title)
        order_idx = 0
        section_page_num = 1

        # Walk child elements of the content container
        for el in content_div.descendants:
            if not isinstance(el, bs4.Tag):
                continue

            tag_name = el.name.lower()

            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                h_text = el.get_text(" ", strip=True)
                if not h_text:
                    continue
                level = int(tag_name[1])

                # Anchor
                anchor_attr = el.get("id") or slugify(h_text)
                current_anchor = anchor_attr
                current_section = h_text

                # Update heading stack
                if level == 1:
                    heading_stack = [h_text]
                elif level == 2:
                    heading_stack = heading_stack[:1] + [h_text]
                elif level == 3:
                    heading_stack = heading_stack[:2] + [h_text]
                else:
                    heading_stack = heading_stack[:3] + [h_text]

                section_page_num += 1
                b = Block(
                    id=f"{doc_id}_p{section_page_num}_b{order_idx}",
                    doc_id=doc_id,
                    page=section_page_num,
                    bbox=(0.0, 0.0, 100.0, 20.0),
                    type=BlockType.HEADING,
                    text=h_text,
                    level=level,
                    order=order_idx,
                    meta={
                        "source": "web_wiki_index",
                        "url": f"{page_url}#{current_anchor}",
                        "section": h_text,
                        "headings": list(heading_stack),
                        "slug": clean_slug,
                    },
                )
                blocks.append(b)
                order_idx += 1

            elif tag_name in ("ul", "ol") and el.parent and el.parent.name not in ("li", "nav"):
                # Process list items under this heading
                list_items = el.find_all("li", recursive=False)
                if not list_items:
                    continue

                for li in list_items:
                    li_text = li.get_text(" ", strip=True)
                    if not li_text or len(li_text) < 3:
                        continue

                    # Extract all hyperlinks
                    a_tags = li.find_all("a", href=True)
                    if not a_tags:
                        # Plain text item
                        b = Block(
                            id=f"{doc_id}_p{section_page_num}_b{order_idx}",
                            doc_id=doc_id,
                            page=section_page_num,
                            bbox=(0.0, 0.0, 100.0, 20.0),
                            type=BlockType.TEXT,
                            text=li_text,
                            order=order_idx,
                            meta={
                                "source": "web_wiki_index",
                                "url": f"{page_url}#{current_anchor}",
                                "section": current_section,
                                "headings": list(heading_stack),
                                "slug": clean_slug,
                            },
                        )
                        blocks.append(b)
                        order_idx += 1
                        continue

                    # First link is the primary resource
                    primary_a = a_tags[0]
                    res_title = primary_a.get_text(strip=True) or "Resource"
                    res_url = primary_a["href"]
                    if not res_url.startswith("http://") and not res_url.startswith("https://"):
                        res_url = urljoin(page_url, res_url)

                    # Sublinks (GitHub, Discord, Reddit, Docs, etc.)
                    sublinks: list[dict[str, str]] = []
                    for extra_a in a_tags[1:]:
                        extra_title = extra_a.get_text(strip=True)
                        extra_href = extra_a["href"]
                        if not extra_href.startswith("http://") and not extra_href.startswith("https://"):
                            extra_href = urljoin(page_url, extra_href)
                        if extra_title and extra_href:
                            sublinks.append({"title": extra_title, "url": extra_href})

                    # Clean description text
                    desc_part = li_text
                    if desc_part.startswith(res_title):
                        desc_part = desc_part[len(res_title):].lstrip(" -:/")

                    wiki_anchor_url = f"{page_url}#{current_anchor}"

                    res_obj = WebResourceLink(
                        title=res_title,
                        url=res_url,
                        description=desc_part,
                        wiki_url=wiki_anchor_url,
                        category=clean_slug,
                        section=current_section,
                        sublinks=sublinks,
                    )
                    resources.append(res_obj)

                    # Compose rich structured chunk text optimized for dual retrieval (dense + BM25)
                    sublink_str = ", ".join(f"{sl['title']}: {sl['url']}" for sl in sublinks)
                    chunk_text = (
                        f"Resource: {res_title}\n"
                        f"URL: {res_url}\n"
                        f"Category: {' > '.join(heading_stack)}\n"
                        f"Details: {desc_part}\n"
                        f"Wiki Source: {wiki_anchor_url}"
                    )
                    if sublink_str:
                        chunk_text += f"\nAuxiliary Links: {sublink_str}"

                    meta_dict: dict[str, Any] = {
                        "source": "web_wiki_index",
                        "is_web": True,
                        "resource_title": res_title,
                        "resource_url": res_url,
                        "wiki_url": wiki_anchor_url,
                        "section": current_section,
                        "headings": list(heading_stack),
                        "slug": clean_slug,
                        "sublinks": sublinks,
                    }

                    b = Block(
                        id=f"{doc_id}_p{section_page_num}_b{order_idx}",
                        doc_id=doc_id,
                        page=section_page_num,
                        bbox=(0.0, 0.0, 100.0, 20.0),
                        type=BlockType.TEXT,
                        text=chunk_text,
                        order=order_idx,
                        meta=meta_dict,
                    )
                    blocks.append(b)
                    order_idx += 1

            elif tag_name == "p" and el.parent and el.parent.name not in ("li", "nav"):
                p_text = el.get_text(" ", strip=True)
                # Ignore empty or tiny paragraphs or boilerplate copyright
                if len(p_text) > 25 and "Copyright" not in p_text and "Powered by" not in p_text:
                    b = Block(
                        id=f"{doc_id}_p{section_page_num}_b{order_idx}",
                        doc_id=doc_id,
                        page=section_page_num,
                        bbox=(0.0, 0.0, 100.0, 20.0),
                        type=BlockType.TEXT,
                        text=f"[{' > '.join(heading_stack)}] {p_text}",
                        order=order_idx,
                        meta={
                            "source": "web_wiki_index",
                            "url": f"{page_url}#{current_anchor}",
                            "section": current_section,
                            "headings": list(heading_stack),
                            "slug": clean_slug,
                        },
                    )
                    blocks.append(b)
                    order_idx += 1

        now_iso = datetime.now(timezone.utc).isoformat()
        doc = WebPageDocument(
            url=page_url,
            slug=clean_slug,
            doc_id=doc_id,
            title=title,
            category=clean_slug,
            resource_count=len(resources),
            blocks_count=len(blocks),
            resources=resources,
            last_synced=now_iso,
            source="web_wiki_index",
        )

        logger.info(
            f"WikiIndexWebParser parsed '{slug}': {len(blocks)} blocks, "
            f"{len(resources)} resources from {page_url}"
        )
        return doc, blocks
