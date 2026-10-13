"""Crawled-page markdown -> Blocks (IRA-68).

A crawled page has no PDF pages or bounding boxes, so provenance follows the wiki-index parser's
convention (`web_parser.py`): `page` counts top-level sections, `bbox` is a constant placeholder, and
the real citation target lives in `meta` — `url` is the page URL plus the heading anchor, and
`is_web` makes retrieval flag the citation as a web source. Both UIs already render those without a
page image.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from contracts.document import Block, BlockType

PLACEHOLDER_BBOX = (0.0, 0.0, 100.0, 20.0)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def web_doc_id(url: str, markdown: str) -> str:
    """`web_crawl_<host>_<hash>` — content-addressed like every doc_id, so re-adding an unchanged page
    is a no-op. The `web_` prefix makes the UIs treat it as a web source; `crawl` keeps it out of the
    shared wiki-index corpus (those ids are `web_wiki_index_*`)."""
    host = slugify(urlparse(url).netloc) or "page"
    digest = hashlib.sha256(f"{url}\n{markdown}".encode("utf-8")).hexdigest()[:8]
    return f"web_crawl_{host}_{digest}"


def _plain(text: str) -> str:
    """Drops images and link targets (the URL is provenance, not searchable prose)."""
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def markdown_to_blocks(markdown: str, doc_id: str, url: str, title: str = "") -> list[Block]:
    blocks: list[Block] = []
    state = {"order": 0, "page": 1}
    trail: list[tuple[int, str]] = []  # (level, heading text) breadcrumb
    anchor = ""

    def meta() -> dict:
        return {
            "is_web": True,
            "source": "crawl4ai",
            "web_url": url,
            "url": f"{url}#{anchor}" if anchor else url,
            "headings": [h for _, h in trail],
            "page_title": title,
        }

    def add(kind: BlockType, text: str, level: int | None = None, html: str | None = None) -> None:
        text = text.strip()
        if not text:
            return
        blocks.append(
            Block(
                id=f"{doc_id}_p{state['page']}_b{state['order']}",
                doc_id=doc_id,
                page=state["page"],
                bbox=PLACEHOLDER_BBOX,
                type=kind,
                text=text,
                html=html,
                level=level,
                order=state["order"],
                meta=meta(),
            )
        )
        state["order"] += 1

    para: list[str] = []
    table: list[str] = []
    code: list[str] | None = None

    def flush_para() -> None:
        if para:
            add(BlockType.TEXT, _plain("\n".join(para)))
            para.clear()

    def flush_table() -> None:
        if table:
            add(BlockType.TABLE, "\n".join(_plain(r) for r in table))
            table.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()

        if code is not None:  # inside a fenced block: keep everything verbatim until the closing fence
            if _FENCE.match(line):
                add(BlockType.CODE, "\n".join(code))
                code = None
            else:
                code.append(raw)
            continue
        if _FENCE.match(line):
            flush_para()
            flush_table()
            code = []
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_para()
            flush_table()
            level, text = len(heading.group(1)), _plain(heading.group(2))
            if not text:
                continue
            if level <= 2 and blocks:
                state["page"] += 1  # a new top-level section is the closest thing a web page has to a page
            while trail and trail[-1][0] >= level:
                trail.pop()
            trail.append((level, text))
            anchor = slugify(text)
            add(BlockType.HEADING, text, level=level)
            continue

        if _TABLE_ROW.match(line):
            flush_para()
            table.append(line)
            continue
        flush_table()

        if not line.strip():
            flush_para()
        elif _LIST_ITEM.match(line) and para and not _LIST_ITEM.match(para[-1]):
            flush_para()
            para.append(line)
        else:
            para.append(line)

    if code:  # unterminated fence at EOF
        add(BlockType.CODE, "\n".join(code))
    flush_para()
    flush_table()
    return blocks
