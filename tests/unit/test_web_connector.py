"""Website connector (IRA-57): extraction, crawling, sync lifecycle and API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contracts.connector import CrawlScope
from contracts.document import BlockType
from services.common.config import ConnectorsConfig
from services.connectors.web import renderer
from services.connectors.web.crawler import Crawler, CrawlSettings
from services.connectors.web.extractor import extract, normalize_url
from services.connectors.web.service import WebConnectorService
from services.connectors.web.store import ConnectorStore
from services.gateway import api
from services.ingestion.url_source import FetchedPage, UrlSourceError
from tests.unit.conftest import TEST_USER

SETTINGS = CrawlSettings(user_agent="test", timeout_s=1, max_page_bytes=1_000_000, delay_s=0, browser_timeout_s=1, min_words=5)


def page(title: str, body: str, links: list[str] = ()) -> str:
    nav = "".join(f'<a href="{href}">{href}</a>' for href in links)
    return (f"<html><head><title>{title}</title></head><body><nav>{nav}</nav>"
            f"<main><h1>{title}</h1>{body}</main><footer>(c) site</footer></body></html>")


LONG = " ".join(["word"] * 30)


class FakeSite:
    """url -> html (or bytes for PDFs); unknown URLs 404."""

    def __init__(self, pages: dict[str, str | bytes], robots: str = "", sitemap: list[str] = ()):
        self.pages = pages
        self.robots = robots
        self.sitemap = sitemap
        self.fetched: list[str] = []

    def __call__(self, url, *, max_bytes, timeout_s, max_redirects):
        self.fetched.append(url)
        if url.endswith("/robots.txt"):
            if not self.robots:
                raise UrlSourceError("The page returned HTTP 404.")
            return FetchedPage(url=url, content_type="text/plain", body=self.robots.encode())
        if url.endswith("/sitemap.xml"):
            if not self.sitemap:
                raise UrlSourceError("The page returned HTTP 404.")
            xml = "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in self.sitemap) + "</urlset>"
            return FetchedPage(url=url, content_type="application/xml", body=xml.encode())
        key = normalize_url(url)
        if key not in self.pages:
            raise UrlSourceError("The page returned HTTP 404.")
        content = self.pages[key]
        if isinstance(content, bytes):
            return FetchedPage(url=key, content_type="application/pdf", body=content)
        return FetchedPage(url=key, content_type="text/html", body=content.encode())


# ---------------------------------------------------------------------------------------- extraction


def test_extraction_keeps_structure_and_drops_boilerplate():
    html = """<html><head><title>T</title></head><body class="layout-with-sidebar">
    <div id="cookie-consent">Accept cookies?</div><aside class="sidebar"><a href="/a">A</a></aside>
    <main><h1 id="top">Falcon</h1><p>The Falcon cluster has 48 GB of memory for retrieval workloads.</p>
    <h2 id="perf">Perf</h2><table><tr><th>Metric</th><th>Value</th></tr><tr><td>qps</td><td>212</td></tr></table>
    <pre><code>falcon start --port 8080</code></pre>
    <div><span>Note:</span> <span>restart the agent after upgrading the driver.</span></div></main>
    <div class="related-posts"><a href="/x">x</a></div><footer>Copyright</footer><script>t()</script></body></html>"""
    p = extract(html, "https://example.com/docs/falcon")
    kinds = [(b.type, b.text) for b in p.blocks]
    assert (BlockType.HEADING, "Falcon") in kinds and (BlockType.HEADING, "Perf") in kinds
    table = next(b for b in p.blocks if b.type == BlockType.TABLE)
    assert table.text.splitlines()[0] == "| Metric | Value |" and "| qps | 212 |" in table.text
    assert table.meta["section"] == "Falcon > Perf" and table.meta["section_url"].endswith("#perf")
    assert any(b.type == BlockType.CODE and b.text == "falcon start --port 8080" for b in p.blocks)
    assert any("restart the agent" in b.text for b in p.blocks)
    joined = p.text.lower()
    for junk in ("cookies", "copyright", "t()"):
        assert junk not in joined
    assert all(b.meta["url"] == "https://example.com/docs/falcon" for b in p.blocks)


def test_real_world_markup_permalinks_inline_code_and_highlighted_code():
    html = """<html><head><meta property="og:title" content="Data Structures"><meta name="description" content="d"></head>
    <body><main><h2 id="lists">5.1. More on Lists<a class="headerlink" href="#lists">¶</a></h2>
    <dl><dt><code>list.</code><code>append</code>(<em>value</em>, /)</dt><dd><p>Add an item to the end of the list.</p></dd></dl>
    <div class="highlight"><pre><span class="gp">&gt;&gt;&gt; </span><span class="n">fruits</span><span class="o">.</span><span class="n">count</span>(<span class="s1">'apple'</span>)
<span class="go">2</span></pre></div>
    <p>One sentence.</p><p>Another sentence.</p></main></body></html>"""
    p = extract(html, "https://docs.example.com/tutorial")
    assert p.title == "Data Structures" and p.description == "d"
    heading = next(b for b in p.blocks if b.type == BlockType.HEADING)
    assert heading.text == "5.1. More on Lists" and heading.meta["section_url"].endswith("#lists")
    assert any(b.text.startswith("list.append(value, /): Add an item") for b in p.blocks)
    code = next(b for b in p.blocks if b.type == BlockType.CODE)
    assert code.text == ">>> fruits.count('apple')\n2"
    assert "sentence.Another" not in p.text


def test_connector_citations_link_to_the_section():
    from services.retrieval.rrf import reciprocal_rank_fusion

    payload = {"id": "c1", "doc_id": "docs_example_com_x_1234abcd", "page": 1, "bbox": [0, 0, 600, 18], "text": "t",
               "meta": {"source": "web_connector", "url": "https://docs.example.com/x",
                        "section_url": "https://docs.example.com/x#install"}}
    cand = reciprocal_rank_fusion([(payload, 0.9)], [])[0]
    assert cand.is_web and cand.web_url == "https://docs.example.com/x#install"


def test_a_javascript_shell_is_flagged():
    shell = '<html><body><div id="root"></div><script src="a.js"></script><script src="b.js"></script><script>boot()</script></body></html>'
    assert extract(shell, "https://spa.example.com/").needs_js


def test_url_normalization_drops_tracking_and_fragments():
    assert normalize_url("HTTPS://Example.com/docs/?utm_source=x&id=2#top") == "https://example.com/docs?id=2"
    assert normalize_url("https://example.com/") == "https://example.com/"


# ---------------------------------------------------------------------------------------- crawling


def crawl(site: FakeSite, start="https://example.com/docs", scope: CrawlScope | None = None, render="auto", render_page=None):
    crawler = Crawler(start, scope or CrawlScope(path_prefix="/docs"), render, SETTINGS, fetch=site, render_page=render_page)
    if render_page is None:
        crawler._render = None
    results = list(crawler.run())
    return crawler, {r.url: r for r in results}


def test_crawl_stays_in_scope_and_honors_robots_and_sitemap():
    site = FakeSite(
        {
            "https://example.com/docs": page("Home", f"<p>{LONG}</p>", ["/docs/a", "/docs/private/x", "/blog/post", "https://other.com/docs"]),
            "https://example.com/docs/a": page("A", f"<p>alpha {LONG}</p>", ["/docs/b"]),
            "https://example.com/docs/b": page("B", f"<p>beta {LONG}</p>"),
            "https://example.com/docs/from-sitemap": page("S", f"<p>sitemap {LONG}</p>"),
            "https://example.com/docs/private/x": page("P", f"<p>{LONG}</p>"),
            "https://example.com/blog/post": page("Blog", f"<p>{LONG}</p>"),
        },
        robots="User-agent: *\nDisallow: /docs/private\n",
        sitemap=["https://example.com/docs/from-sitemap", "https://example.com/blog/x"],
    )
    crawler, results = crawl(site)
    assert crawler.complete
    indexed = {u for u, r in results.items() if r.kind == "html"}
    assert indexed == {"https://example.com/docs", "https://example.com/docs/a", "https://example.com/docs/b",
                       "https://example.com/docs/from-sitemap"}
    assert results["https://example.com/docs/private/x"].error == "disallowed by robots.txt"
    assert "https://example.com/blog/post" not in site.fetched and not any("other.com" in u for u in site.fetched)


def test_page_cap_marks_the_crawl_incomplete_and_depth_is_limited():
    pages = {"https://example.com/docs": page("Home", f"<p>{LONG}</p>", [f"/docs/{i}" for i in range(5)])}
    pages.update({f"https://example.com/docs/{i}": page(str(i), f"<p>{i} {LONG}</p>", [f"/docs/{i}/deep"]) for i in range(5)})
    crawler, results = crawl(FakeSite(pages), scope=CrawlScope(path_prefix="/docs", max_pages=3))
    assert not crawler.complete and len(results) == 3
    _, results = crawl(FakeSite(pages), scope=CrawlScope(path_prefix="/docs", max_depth=1))
    assert not any(u.endswith("/deep") for u in results)


def test_duplicate_content_and_pdfs():
    same = f"<p>identical {LONG}</p>"
    site = FakeSite({
        "https://example.com/docs": page("Home", same, ["/docs/copy", "/docs/manual.pdf"]),
        "https://example.com/docs/copy": page("Home", same),
        "https://example.com/docs/manual.pdf": b"%PDF-1.4 fake",
    })
    _, results = crawl(site)
    assert results["https://example.com/docs/copy"].kind == "skipped"
    assert results["https://example.com/docs/manual.pdf"].kind == "pdf"


def test_javascript_pages_use_the_browser_when_available():
    shell = '<html><body><div id="root"></div><script>a()</script><script>b()</script><script>c()</script></body></html>'
    site = FakeSite({"https://example.com/docs": shell})
    _, results = crawl(site)
    assert results["https://example.com/docs"].needs_js

    rendered = page("Rendered", f"<p>now visible {LONG}</p>")
    _, results = crawl(site, render_page=lambda url, **_: (url, rendered))
    r = results["https://example.com/docs"]
    assert r.rendered_with == "browser" and not r.needs_js and "now visible" in r.page.text


def test_browser_requests_to_internal_hosts_are_blocked():
    assert not renderer._allowed("http://127.0.0.1:6333/collections")
    assert not renderer._allowed("http://169.254.169.254/latest/meta-data")
    assert not renderer._allowed("file:///etc/passwd")
    assert renderer._allowed("data:text/plain,hi")


# ---------------------------------------------------------------------------------------- sync lifecycle


class FakeIndexing:
    def __init__(self):
        self.indexed: dict[str, list] = {}
        self.removed: list[str] = []

    def chunk_and_index(self, doc_id, blocks):
        self.indexed[doc_id] = blocks

    def remove_document(self, doc_id):
        self.removed.append(doc_id)


@pytest.fixture
def setup(identity, tmp_path):
    site = FakeSite({})
    indexing = FakeIndexing()
    store = ConnectorStore(lambda: None)
    service = WebConnectorService(
        store=store, indexing=lambda: indexing, identity=lambda: identity, sessions=api.session_manager,
        ingestion=lambda: None, config=ConnectorsConfig(crawl_delay_s=0, min_words=5),
        crawler_factory=lambda url, scope, render, settings: Crawler(url, scope, render, SETTINGS, fetch=site, render_page=None),
        data_dir=tmp_path,
    )
    return site, indexing, service


def make_connector(service, project_id=None):
    from contracts.connector import WebConnector

    c = WebConnector(name="docs", start_url="https://example.com/docs", owner_id=TEST_USER.id,
                     project_id=project_id, scope=CrawlScope(path_prefix="/docs"))
    return service.store.save(c)


def test_sync_indexes_then_skips_unchanged_then_replaces_changed_and_removes_gone(setup, identity):
    site, indexing, service = setup
    site.pages = {
        "https://example.com/docs": page("Home", f"<p>home {LONG}</p>", ["/docs/a", "/docs/b"]),
        "https://example.com/docs/a": page("A", f"<p>alpha {LONG}</p>"),
        "https://example.com/docs/b": page("B", f"<p>beta {LONG}</p>"),
    }
    project = api.session_manager.create_session(title="p", owner_id=TEST_USER.id)
    c = make_connector(service, project_id=project.id)

    r1 = service.sync(c.id)
    assert (r1.indexed, r1.unchanged, r1.status) == (3, 0, "ok")
    first_ids = set(indexing.indexed)
    assert first_ids <= identity.owned_doc_ids(TEST_USER.id)
    assert set(api.session_manager.get_session(project.id)[0].files) == first_ids
    blocks = next(iter(indexing.indexed.values()))
    assert all(b.meta["url"].startswith("https://example.com/docs") for b in blocks)

    r2 = service.sync(c.id)
    assert (r2.indexed, r2.unchanged) == (0, 3) and indexing.removed == []

    a_old = next(p.doc_id for p in service.store.pages(c.id).values() if p.url.endswith("/a"))
    b_old = next(p.doc_id for p in service.store.pages(c.id).values() if p.url.endswith("/b"))
    site.pages["https://example.com/docs/a"] = page("A", f"<p>alpha CHANGED {LONG}</p>")
    site.pages["https://example.com/docs"] = page("Home", f"<p>home {LONG}</p>", ["/docs/a"])  # b unlinked
    del site.pages["https://example.com/docs/b"]
    r3 = service.sync(c.id)
    assert r3.indexed == 1 and r3.removed == 1
    assert {a_old, b_old} <= set(indexing.removed)
    owned = identity.owned_doc_ids(TEST_USER.id)
    assert a_old not in owned and b_old not in owned
    files = set(api.session_manager.get_session(project.id)[0].files)
    assert a_old not in files and b_old not in files and len(files) == 2
    assert service.store.get(c.id).page_count == 2


def test_a_partial_crawl_does_not_delete_unreached_pages(setup):
    site, indexing, service = setup
    site.pages = {"https://example.com/docs": page("Home", f"<p>{LONG}</p>", [f"/docs/{i}" for i in range(4)])}
    site.pages.update({f"https://example.com/docs/{i}": page(str(i), f"<p>{i} {LONG}</p>") for i in range(4)})
    c = make_connector(service)
    service.sync(c.id)
    service.store.save(c.model_copy(update={"scope": CrawlScope(path_prefix="/docs", max_pages=2)}))
    report = service.sync(c.id)
    assert report.removed == 0 and indexing.removed == []
    assert len(service.store.pages(c.id)) == 5


def test_identical_content_owned_elsewhere_stays_in_the_index(setup, identity):
    from contracts.identity import OwnedDocument

    site, indexing, service = setup
    site.pages = {"https://example.com/docs": page("Home", f"<p>{LONG}</p>")}
    c = make_connector(service)
    service.sync(c.id)
    doc_id = next(iter(indexing.indexed))
    identity.add_document(OwnedDocument(user_id="usr_other", doc_id=doc_id, filename="x", path="x"))
    service.delete(c)
    assert doc_id not in identity.owned_doc_ids(TEST_USER.id) and indexing.removed == []


# ---------------------------------------------------------------------------------------- API

client = TestClient(api.app)


@pytest.fixture
def api_service(setup, monkeypatch):
    site, indexing, service = setup
    monkeypatch.setattr(api, "_connector_service", service)
    return site, indexing, service


def test_api_refuses_internal_urls_and_hides_other_users_connectors(api_service):
    assert client.post("/api/v1/connectors", json={"start_url": "http://127.0.0.1:6379/"}).status_code == 422
    assert client.post("/api/v1/connectors", json={"start_url": "file:///etc/passwd"}).status_code == 422
    created = client.post("/api/v1/connectors", json={"start_url": "example.com/docs/", "sync_now": False}).json()
    assert created["start_url"] == "https://example.com/docs" and created["scope"]["path_prefix"] == "/"
    assert created["name"] == "example.com" and created["status"] == "idle"

    from contracts.identity import User

    other = User(id="usr_other", email="o@example.com")
    api.app.dependency_overrides[api.optional_user] = lambda: other
    assert client.get(f"/api/v1/connectors/{created['id']}").status_code == 404
    assert client.get("/api/v1/connectors").json()["connectors"] == []


def test_api_sync_lists_pages_and_marks_library_entries_as_web(api_service):
    site, _, service = api_service
    site.pages = {"https://example.com/docs": page("Home", f"<p>home {LONG}</p>", ["/docs/a"]),
                  "https://example.com/docs/a": page("Alpha page", f"<p>alpha {LONG}</p>")}
    created = client.post("/api/v1/connectors", json={"start_url": "https://example.com/docs", "schedule": "daily"}).json()
    assert created["status"] == "queued"  # background sync ran after the response
    detail = client.get(f"/api/v1/connectors/{created['id']}").json()
    assert detail["connector"]["status"] == "ok" and detail["connector"]["next_sync_at"]
    assert {p["status"] for p in detail["pages"]} == {"indexed"} and len(detail["pages"]) == 2
    assert detail["last_report"]["indexed"] == 2

    docs = client.get("/api/v1/documents").json()["documents"]
    web = [d for d in docs if d.get("connector_id") == created["id"]]
    assert {d["url"] for d in web} == {"https://example.com/docs", "https://example.com/docs/a"}
    assert all(d["is_web"] for d in web) and "Alpha page" in {d["name"] for d in web}

    service.store.save(service.store.get(created["id"]).model_copy(update={"status": "running"}))
    assert client.post(f"/api/v1/connectors/{created['id']}/sync").status_code == 409


def test_api_delete_removes_pages_from_the_library(api_service):
    site, indexing, _ = api_service
    site.pages = {"https://example.com/docs": page("Home", f"<p>{LONG}</p>")}
    cid = client.post("/api/v1/connectors", json={"start_url": "https://example.com/docs"}).json()["id"]
    assert client.delete(f"/api/v1/connectors/{cid}").json() == {"deleted": True}
    assert client.get(f"/api/v1/connectors/{cid}").status_code == 404
    assert not [d for d in client.get("/api/v1/documents").json()["documents"] if d.get("connector_id") == cid]
    assert len(indexing.removed) == 1
