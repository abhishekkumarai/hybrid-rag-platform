"""IRA-68: crawled markdown becomes blocks that cite the page URL + heading anchor."""

from contracts.document import BlockType
from services.ingestion.web_markdown import markdown_to_blocks, slugify, web_doc_id

URL = "https://example.org/guide"
MD = """# Falcon Guide

Intro paragraph about [peregrine falcons](https://example.org/p) with an ![img](x.png) image.

## Nesting

- ledges on cliffs
- tall buildings

| Site | Pairs |
|------|-------|
| Cliff | 4 |

```python
print("nest")
```

## Diet

Falcons hunt pigeons.
"""


def _blocks():
    return markdown_to_blocks(MD, "web_crawl_example_org_ab12cd34", URL, title="Falcon Guide")


def test_block_types_and_levels():
    blocks = _blocks()
    kinds = [(b.type, b.level) for b in blocks]
    assert kinds[0] == (BlockType.HEADING, 1)
    assert (BlockType.HEADING, 2) in kinds
    assert any(b.type == BlockType.TABLE and "Cliff" in b.text for b in blocks)
    assert any(b.type == BlockType.CODE and b.text == 'print("nest")' for b in blocks)


def test_links_and_images_are_stripped_from_text():
    intro = next(b for b in _blocks() if b.text.startswith("Intro"))
    assert "peregrine falcons" in intro.text
    assert "example.org/p" not in intro.text and "img" not in intro.text


def test_citation_target_is_url_with_heading_anchor():
    blocks = _blocks()
    diet = next(b for b in blocks if b.text.startswith("Falcons hunt"))
    assert diet.meta["is_web"] is True
    assert diet.meta["url"] == f"{URL}#diet"
    assert diet.meta["web_url"] == URL
    assert diet.meta["headings"] == ["Falcon Guide", "Diet"]
    assert diet.meta["source"] == "crawl4ai"


def test_pages_count_top_level_sections_and_ids_are_unique():
    blocks = _blocks()
    assert [b.page for b in blocks][0] == 1
    assert max(b.page for b in blocks) >= 3
    assert len({b.id for b in blocks}) == len(blocks)
    assert all(len(b.bbox) == 4 for b in blocks)


def test_doc_id_is_web_prefixed_but_not_wiki_and_content_addressed():
    a = web_doc_id(URL, MD)
    assert a.startswith("web_crawl_example-org_") or a.startswith("web_crawl_")
    assert not a.startswith("web_wiki_index")
    assert a == web_doc_id(URL, MD)
    assert a != web_doc_id(URL, MD + "\nmore")


def test_empty_markdown_gives_no_blocks_and_slugify():
    assert markdown_to_blocks("  \n\n", "d", URL) == []
    assert slugify("Hello, World!") == "hello-world"
