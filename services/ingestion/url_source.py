"""Turns a user-supplied URL into a PDF so it can go through the normal ingestion pipeline.

The gateway runs next to Qdrant, Redis and the Docker host, so fetching an arbitrary URL is an SSRF
risk. Every hop (including redirects) must be http(s) and resolve only to public addresses, and the
socket actually connected to is re-checked before the body is read, so a hostname that re-resolves
to a private address between the check and the connect (DNS rebinding) is still refused.
"""

from __future__ import annotations

import io
import ipaddress
import re
import socket
from dataclasses import dataclass
from html import escape
from urllib.parse import urljoin, urlparse

import bs4
import fitz
import requests

from services.common.logger import get_logger

logger = get_logger("ingestion.url_source")

_USER_AGENT = "IRA-RAG/1.0 (+document ingestion)"
_KEEP_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td",
    "th", "pre", "code", "blockquote", "strong", "em", "b", "i", "br",
}
_DROP_TAGS = ["script", "style", "noscript", "iframe", "svg", "form", "nav", "footer", "header", "aside", "button"]


class UrlSourceError(ValueError):
    """The URL can't be ingested; the message is safe to show to the user."""


@dataclass
class FetchedPage:
    url: str
    content_type: str
    body: bytes


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def check_public_url(url: str) -> None:
    """Raises UrlSourceError unless `url` is http(s) and its host resolves only to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UrlSourceError("Only http:// and https:// URLs can be added.")
    if parsed.username or parsed.password:
        raise UrlSourceError("URLs with embedded credentials aren't allowed.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UrlSourceError(f"Couldn't resolve {parsed.hostname}.") from exc
    ips = {info[4][0] for info in infos}
    if not ips or not all(_is_public(ip) for ip in ips):
        raise UrlSourceError("That address isn't publicly reachable, so it can't be added.")


def _peer_ip(resp: requests.Response) -> str | None:
    try:
        return resp.raw._connection.sock.getpeername()[0]  # type: ignore[union-attr]
    except Exception:
        return None


def fetch_public_url(url: str, *, max_bytes: int, timeout_s: float, max_redirects: int) -> FetchedPage:
    """GETs `url`, following redirects by hand so every hop is re-validated."""
    current = url
    for _ in range(max_redirects + 1):
        check_public_url(current)
        try:
            resp = requests.get(
                current, stream=True, allow_redirects=False, timeout=timeout_s,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,text/plain;q=0.8"},
            )
        except requests.RequestException as exc:
            raise UrlSourceError(f"Couldn't fetch the page: {exc.__class__.__name__}.") from exc
        with resp:
            peer = _peer_ip(resp)
            if peer is not None and not _is_public(peer):
                raise UrlSourceError("That address isn't publicly reachable, so it can't be added.")
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise UrlSourceError("The page redirected without a destination.")
                current = urljoin(current, location)
                continue
            if resp.status_code >= 400:
                raise UrlSourceError(f"The page returned HTTP {resp.status_code}.")
            declared = int(resp.headers.get("content-length") or 0)
            if declared > max_bytes:
                raise UrlSourceError(f"The page is larger than {max_bytes // 1_000_000} MB.")
            chunks, size = [], 0
            for chunk in resp.iter_content(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise UrlSourceError(f"The page is larger than {max_bytes // 1_000_000} MB.")
                chunks.append(chunk)
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            return FetchedPage(url=current, content_type=ctype, body=b"".join(chunks))
    raise UrlSourceError("Too many redirects.")


def _clean_html(html: str, source_url: str) -> tuple[str, str]:
    """Reduces a page to its readable content as simple, Story-safe HTML. Returns (title, html)."""
    soup = bs4.BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in root.find_all(True):
        if tag.name == "a":
            tag.unwrap()
        elif tag.name not in _KEEP_TAGS:
            tag.unwrap()
        else:
            tag.attrs = {}
    body = str(root)
    if not title:
        h1 = root.find("h1") if hasattr(root, "find") else None
        title = h1.get_text(" ", strip=True) if h1 else (urlparse(source_url).hostname or "Web page")
    header = f"<h1>{escape(title)}</h1><p><i>Source: {escape(source_url)}</i></p>"
    return title, header + body


def html_to_pdf(html: str, source_url: str) -> tuple[str, bytes]:
    """Lays readable HTML out as A4 pages. Returns (title, pdf_bytes)."""
    title, cleaned = _clean_html(html, source_url)
    story = fitz.Story(html=cleaned, user_css="body{font-family:sans-serif;font-size:10pt;} pre{white-space:pre-wrap;}")
    page_rect = fitz.paper_rect("a4")
    content = page_rect + (50, 50, -50, -50)
    out = io.BytesIO()
    writer = fitz.DocumentWriter(out)
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()
    pdf = fitz.open("pdf", out.getvalue())
    if not pdf.page_count or not "".join(p.get_text() for p in pdf).strip():
        raise UrlSourceError("No readable text was found on that page.")
    pdf.set_metadata({"title": title, "subject": source_url})
    data = pdf.tobytes(garbage=3, deflate=True, no_new_id=True)
    pdf.close()
    return title, data


def filename_for(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.hostname or 'web'}{parsed.path}".rstrip("/") or (parsed.hostname or "web")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower()[:80] or "web_page"
    return f"{stem}.pdf"


def url_to_pdf(url: str, *, max_bytes: int, timeout_s: float, max_redirects: int) -> tuple[str, bytes]:
    """Fetches `url` and returns (filename, pdf_bytes). PDFs are passed through; HTML/text is laid out."""
    page = fetch_public_url(url, max_bytes=max_bytes, timeout_s=timeout_s, max_redirects=max_redirects)
    if page.content_type == "application/pdf" or page.body.startswith(b"%PDF"):
        return filename_for(page.url), page.body
    if page.content_type in ("text/html", "application/xhtml+xml", ""):
        html = page.body.decode("utf-8", errors="replace")
    elif page.content_type.startswith("text/"):
        text = page.body.decode("utf-8", errors="replace")
        html = f"<pre>{escape(text)}</pre>"
    else:
        raise UrlSourceError(f"Unsupported content type '{page.content_type}'. Add a web page or a PDF link.")
    title, pdf = html_to_pdf(html, page.url)
    logger.info(f"URL source: {page.url} -> '{title}' ({len(page.body)} bytes -> {len(pdf)} byte PDF)")
    return filename_for(page.url), pdf
