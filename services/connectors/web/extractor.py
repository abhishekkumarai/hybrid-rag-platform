"""HTML -> clean, structured blocks (IRA-57).

Finds the page's main content (not nav, footers, cookie banners, sidebars), then walks it in reading
order emitting typed blocks: headings with their level and section anchor, paragraphs, lists, tables as
markdown (the chunker splits large tables with a repeated header row), and code verbatim. Every block
carries the page URL, so citations link back to the exact page and, when the section has an id, the
section within it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import bs4
from bs4 import BeautifulSoup, NavigableString, Tag

from contracts.document import Block, BlockType

_DROP_TAGS = (
    "script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed",
    "form", "button", "input", "select", "textarea", "nav", "footer", "aside", "dialog", "link", "meta",
)
_DROP_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "alertdialog", "menu", "menubar"}
# Matched against class/id *tokens*, so "nav" hits "site-nav" but not "canvas".
_BOILERPLATE = re.compile(
    r"(^|[-_])(nav|navbar|menu|breadcrumbs?|footer|sidebar|side-?bar|cookie|consent|gdpr|banner|advert|ads?|"
    r"promo|share|sharing|social|related|comments?|newsletter|subscribe|popup|modal|skip-?link|toc|"
    r"table-of-contents|pagination|pager|edit-?page|feedback|announcement)($|[-_])",
    re.I,
)
_CONTENT_HINT = re.compile(r"(^|[-_])(content|main|article|post|entry|docs?|documentation|markdown|prose|body-?text)($|[-_])", re.I)
_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "pre", "table", "blockquote", "figure"}
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)", re.I)


@dataclass
class ExtractedPage:
    url: str
    title: str
    blocks: list[Block]
    links: list[str]
    text: str
    canonical: str | None = None
    description: str | None = None
    lang: str | None = None
    words: int = 0
    needs_js: bool = False
    content_hash: str = ""
    meta: dict = field(default_factory=dict)


def normalize_url(url: str) -> str:
    """Canonical form for de-duplication: no fragment, no tracking params, lowercase host, no trailing '/'
    except at the root."""
    url, _ = urldefrag(url)
    p = urlparse(url)
    query = "&".join(q for q in p.query.split("&") if q and not _TRACKING_PARAMS.match(q.split("=", 1)[0]))
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    netloc = (p.hostname or "").lower() + (f":{p.port}" if p.port and p.port not in (80, 443) else "")
    return p._replace(scheme=p.scheme.lower(), netloc=netloc, path=path, query=query, params="", fragment="").geturl()


def _tokens(tag: Tag) -> str:
    cls = tag.get("class") or []
    return " ".join([*(cls if isinstance(cls, list) else [cls]), str(tag.get("id") or "")])


def _is_boilerplate(tag: Tag) -> bool:
    if tag.get("role") in _DROP_ROLES or tag.get("aria-hidden") == "true" or tag.has_attr("hidden"):
        return True
    style = str(tag.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    toks = _tokens(tag).split()
    return any(_BOILERPLATE.search(t) for t in toks) and not any(_CONTENT_HINT.search(t) for t in toks)


_PERMALINK = re.compile(r"\s*[¶#§🔗]+\s*$")
_BLOCK_LEVEL = ("p", "div", "li", "td", "th", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
                "blockquote", "figcaption", "pre", "ul", "ol", "table", "dl")


def _text(node: Tag | NavigableString) -> str:
    # No separator: inline markup (code, links, emphasis) keeps the page's own spacing, so
    # `list.<code>append</code>(x)` stays "list.append(x)". Block boundaries get a space in `_mark_blocks`.
    return re.sub(r"\s+", " ", node.get_text() if isinstance(node, Tag) else str(node)).strip()


def _mark_blocks(root: Tag) -> None:
    """Puts a space after block-level elements and line breaks so adjacent blocks don't fuse words."""
    for br in root.find_all("br"):
        br.replace_with("\n" if br.find_parent("pre") else " ")
    for tag in root.find_all(_BLOCK_LEVEL):
        if tag.name != "pre" and tag.find_parent("pre") is None:
            tag.append(" ")


def _clean_heading(tag: Tag) -> str:
    for a in tag.find_all("a", class_=re.compile(r"(header|heading|anchor|permalink)", re.I)):
        a.decompose()
    return _PERMALINK.sub("", _text(tag))


def _link_density(tag: Tag) -> float:
    total = len(_text(tag)) or 1
    return sum(len(_text(a)) for a in tag.find_all("a")) / total


def _score(tag: Tag) -> float:
    """Readability-style: paragraph text counts, link-heavy text doesn't, content-ish names help."""
    paras = tag.find_all(["p", "pre", "li", "td"], recursive=True)
    text_len = sum(len(_text(p)) for p in paras) or len(_text(tag)) * 0.3
    score = text_len * (1 - min(_link_density(tag), 0.9))
    if _CONTENT_HINT.search(_tokens(tag)):
        score *= 1.25
    return score


def _content_root(soup: BeautifulSoup) -> Tag:
    for sel in ("main", "[role=main]", "article"):
        found = soup.select(sel)
        if len(found) == 1 and len(_text(found[0])) > 200:
            return found[0]
    body = soup.body or soup
    candidates = [t for t in body.find_all(["div", "section", "article", "main"]) if len(_text(t)) > 200]
    if not candidates:
        return body
    best = max(candidates, key=_score)
    # Climb while the parent adds substantially more real content (avoid picking one subsection).
    while isinstance(best.parent, Tag) and best.parent is not body and _score(best.parent) > _score(best) * 1.3:
        best = best.parent
    return best


def _table_markdown(table: Tag) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [_text(c).replace("|", "\\|") for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _list_text(lst: Tag, depth: int = 0) -> str:
    out = []
    ordered = lst.name == "ol"
    for i, li in enumerate(lst.find_all("li", recursive=False), 1):
        own = "".join(_text(c) + " " for c in li.children if not (isinstance(c, Tag) and c.name in ("ul", "ol"))).strip()
        bullet = f"{i}." if ordered else "-"
        if own:
            out.append(f"{'  ' * depth}{bullet} {own}")
        for sub in li.find_all(["ul", "ol"], recursive=False):
            out.append(_list_text(sub, depth + 1))
    return "\n".join(x for x in out if x)


def _anchor(tag: Tag) -> str | None:
    node: Tag | None = tag
    for _ in range(3):
        if node is None:
            break
        if node.get("id"):
            return str(node["id"])
        a = node.find("a", attrs={"name": True}) or node.find(attrs={"id": True})
        if a is not None and a.get("id" if a.has_attr("id") else "name"):
            return str(a.get("id") or a.get("name"))
        node = node.parent if isinstance(node.parent, Tag) else None
    return None


def _looks_js_rendered(soup: BeautifulSoup, words: int) -> bool:
    if words >= 60:
        return False
    scripts = len(soup.find_all("script"))
    mount = soup.select_one("#root, #app, #__next, #__nuxt, [data-reactroot], app-root, #svelte")
    return scripts >= 3 or (mount is not None and len(_text(mount)) < 40) or bool(soup.find("noscript"))


def doc_id_for(url: str, content: str) -> str:
    """`{slug}_{sha256[:8]}` like every other document id, so identical content is shared and an edited
    page becomes a new document."""
    p = urlparse(url)
    slug = re.sub(r"[^a-z0-9]+", "_", f"{p.hostname or 'web'}{p.path}".lower()).strip("_")[:80] or "web_page"
    return f"{slug}_{hashlib.sha256(content.encode('utf-8')).hexdigest()[:8]}"


def extract(html: str, url: str) -> ExtractedPage:
    try:
        soup = BeautifulSoup(html, "lxml")
    except bs4.FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")

    head_title = soup.title.get_text(strip=True) if soup.title else ""
    # Read head metadata now: the cleanup pass below removes <meta>/<link> tags.
    og = soup.find("meta", attrs={"property": "og:title"})
    og_title = str(og.get("content") or "").strip() if og else ""
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in (r if isinstance(r, list) else [r]))
    canonical = urljoin(url, canonical_tag["href"]) if canonical_tag and canonical_tag.get("href") else None
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = str(desc_tag.get("content") or "") if desc_tag else None
    lang = soup.html.get("lang") if soup.html else None

    # Links come from the untouched page so navigation menus still feed the crawler.
    links = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(url, href)
        if urlparse(absolute).scheme in ("http", "https"):
            links.append(normalize_url(absolute))

    for tag in soup(_DROP_TAGS):
        tag.decompose()
    page_len = len(_text(soup.body or soup)) or 1
    for tag in [t for t in soup.find_all(True) if isinstance(t, Tag) and t.attrs is not None and _is_boilerplate(t)]:
        if tag.decomposed:
            continue
        # A wrapper named e.g. "layout-with-sidebar" can hold the whole article: only drop elements that
        # are a small share of the page, or are mostly links (menus, related-post lists).
        share = len(_text(tag)) / page_len
        if share < 0.3 or _link_density(tag) > 0.5:
            tag.decompose()

    root = _content_root(soup)
    _mark_blocks(root)
    h1 = root.find("h1")
    title = og_title or (h1 and _clean_heading(h1)) or head_title or url

    blocks: list[Block] = []
    seen: set[str] = set()
    heading_path: list[str] = []
    section_anchor: str | None = None

    def add(kind: BlockType, text: str, **extra) -> None:
        text = text.strip()
        if not text or (kind != BlockType.HEADING and len(text) < 2):
            return
        key = f"{kind}:{text}"
        if key in seen and kind != BlockType.HEADING:
            return
        seen.add(key)
        order = len(blocks)
        page_url = url + (f"#{section_anchor}" if section_anchor else "")
        blocks.append(Block(
            id=f"web_p1_b{order}",
            doc_id="pending",
            page=1,
            # Web pages have no geometry; a monotonically increasing pseudo-bbox keeps reading order.
            bbox=(0.0, float(order * 20), 600.0, float(order * 20 + 18)),
            type=kind,
            text=text,
            order=order,
            meta={"source": "web_connector", "url": url, "section_url": page_url, "section": " > ".join(heading_path)},
            **extra,
        ))

    def walk(node: Tag) -> None:
        nonlocal section_anchor
        for child in node.children:
            if isinstance(child, NavigableString):
                if isinstance(child, bs4.element.Comment):
                    continue
                txt = _text(child)
                # Loose text sitting between block elements (common in hand-written HTML).
                if len(txt) > 40:
                    add(BlockType.TEXT, txt)
                continue
            if not isinstance(child, Tag) or child.decomposed:
                continue
            name = child.name
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(name[1])
                text = _clean_heading(child)
                if not text:
                    continue
                heading_path[:] = heading_path[: level - 1] + [text]
                section_anchor = _anchor(child) or section_anchor
                add(BlockType.HEADING, text, level=level)
            elif name == "p":
                add(BlockType.TEXT, _text(child))
            elif name in ("ul", "ol"):
                add(BlockType.TEXT, _list_text(child))
            elif name == "dl":
                pairs = [f"{_text(dt)}: {_text(dt.find_next_sibling('dd'))}" for dt in child.find_all("dt")
                         if dt.find_next_sibling("dd") is not None]
                add(BlockType.TEXT, "\n".join(pairs))
            elif name == "pre":
                # <pre> keeps its own whitespace; highlighter <span>s must not add separators.
                add(BlockType.CODE, child.get_text().strip("\n").rstrip())
            elif name == "table":
                md = _table_markdown(child)
                caption = child.find("caption")
                if md:
                    add(BlockType.TABLE, md, html=str(child)[:20000], caption=_text(caption) if caption else None)
            elif name == "blockquote":
                add(BlockType.TEXT, "> " + _text(child))
            elif name == "figure":
                cap = child.find("figcaption")
                img = child.find("img")
                label = _text(cap) if cap else (img.get("alt", "") if img else "")
                if label:
                    add(BlockType.CAPTION, label)
            elif name == "img":
                if child.get("alt") and len(child["alt"]) > 20:
                    add(BlockType.CAPTION, str(child["alt"]))
            elif child.find(list(_BLOCK_TAGS) + ["div", "section", "article", "br"]) is None:
                # "div soup": a container with no block-level children is one paragraph of text.
                add(BlockType.TEXT, _text(child))
            else:
                walk(child)

    walk(root)

    text = "\n".join(b.text for b in blocks)
    words = len(text.split())
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExtractedPage(
        url=url,
        title=title[:300],
        blocks=blocks,
        links=list(dict.fromkeys(links)),
        text=text,
        canonical=normalize_url(canonical) if canonical else None,
        description=description,
        lang=lang,
        words=words,
        needs_js=_looks_js_rendered(soup, words),
        content_hash=content_hash,
    )


def finalize_blocks(page: ExtractedPage, doc_id: str) -> list[Block]:
    """Stamps the document id (known only once content is hashed) onto every block."""
    return [b.model_copy(update={"doc_id": doc_id, "id": f"{doc_id}_p1_b{b.order}"}) for b in page.blocks]
