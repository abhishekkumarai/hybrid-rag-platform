"""IRA-68: Crawl4AI against a real headless Chromium and real local web servers (nothing mocked).

Needs the `crawl` extra and a Chromium install (the Docker image has both); skipped otherwise.
The only substitution is the *address policy*: the real check_public_url rejects 127.0.0.1, so the
tests swap in a policy that allows the "public" test server and refuses the "internal" one. The
browser, the servers and the requests between them are all real.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("crawl4ai")

from contracts.retrieval import SearchQuery  # noqa: E402
from services.indexing.service import IndexingService  # noqa: E402
from services.ingestion import crawler  # noqa: E402
from services.ingestion.url_source import UrlSourceError  # noqa: E402
from services.ingestion.web_markdown import markdown_to_blocks, web_doc_id  # noqa: E402
from services.retrieval.service import RetrievalService  # noqa: E402


class _Server:
    def __init__(self, routes: dict[str, str]):
        self.hits: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                body = routes.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png" if self.path.endswith(".png") else "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self):
        self.httpd.shutdown()


_FILLER = " ".join(
    f"<p>Paragraph {i}: field observers record where raptors roost, how far they range and which prey "
    "they favour across the seasons, then publish the counts so that other surveys can compare them.</p>"
    for i in range(6)
)


def _page(title: str, body: str) -> str:
    # Crawl4AI's anti-bot check rejects very small pages, so test pages carry realistic bulk.
    return f"<html><head><title>{title}</title></head><body>{body}{_FILLER}</body></html>"


@pytest.fixture
def internal():
    server = _Server({"/secret.png": "not-an-image"})
    yield server
    server.stop()


@pytest.fixture
def site(internal, monkeypatch):
    routes: dict[str, str] = {}
    server = _Server(routes)
    routes.update({
        # The facts below are injected by a script, so they are absent from the raw HTML.
        "/": _page("Falcon Census", """
            <h1>Falcon Census</h1><div id="app">loading</div>
            <script>document.getElementById('app').innerHTML =
              '<p>Hydrated census result: 42 breeding pairs counted along the north ridge.</p>';</script>
            <a href="/nesting">Nesting</a> <a href="/diet">Diet</a> <a href="http://localhost:%d/">elsewhere</a>
        """ % server.port),
        "/nesting": _page("Nesting", "<h1>Nesting</h1><p>Nests sit on north-facing cliff ledges.</p>"),
        "/diet": _page("Diet", '<h1>Diet</h1><p>Falcons hunt pigeons.</p><a href="/deep">more</a>'),
        "/deep": _page("Deep", "<h1>Deep</h1><p>Only reachable at depth two.</p>"),
        # A public page that tries to make the browser call the internal server.
        "/leaky": _page("Leaky", f"""
            <h1>Leaky</h1><p>Public content stays.</p><div id="o"></div>
            <script>var i = new Image();
              i.onload = function() {{ document.getElementById('o').textContent = 'LEAKED internal response'; }};
              i.onerror = function() {{ document.getElementById('o').textContent = 'internal blocked'; }};
              i.src = '{internal.base}/secret.png';</script>
        """),
    })

    def policy(url: str) -> None:
        if f":{internal.port}" in url:
            raise UrlSourceError("not publicly reachable")

    monkeypatch.setattr(crawler, "check_public_url", policy)
    yield server
    server.stop()


def test_javascript_rendered_content_is_captured(site):
    pages = crawler.crawl(f"{site.base}/", max_depth=0, max_pages=1)
    assert len(pages) == 1
    assert "42 breeding pairs" in pages[0].markdown, pages[0].markdown
    assert pages[0].title == "Falcon Census"


def test_depth_one_follows_same_site_links_only(site):
    pages = crawler.crawl(f"{site.base}/", max_depth=1, max_pages=10)
    urls = {p.url for p in pages}
    assert f"{site.base}/nesting" in urls and f"{site.base}/diet" in urls
    assert f"{site.base}/deep" not in urls  # two hops away
    assert not any("localhost" in u for u in urls)  # different host: off-site


def test_max_pages_is_a_hard_cap(site):
    assert len(crawler.crawl(f"{site.base}/", max_depth=2, max_pages=2)) == 2


def test_browser_subrequest_to_a_blocked_host_never_happens(site, internal):
    pages = crawler.crawl(f"{site.base}/leaky", max_depth=0, max_pages=1)
    assert "Public content stays." in pages[0].markdown
    assert "LEAKED" not in pages[0].markdown
    assert internal.hits == [], f"the browser reached the internal server: {internal.hits}"


def test_start_url_on_a_blocked_host_is_refused(site, internal):
    with pytest.raises(crawler.CrawlError, match="publicly reachable"):
        crawler.crawl(f"{internal.base}/secret.png")
    assert internal.hits == []


def test_crawled_page_indexes_and_retrieves_with_a_web_citation(site, tmp_path):
    page = crawler.crawl(f"{site.base}/", max_depth=0, max_pages=1)[0]
    doc_id = web_doc_id(page.url, page.markdown)
    blocks = markdown_to_blocks(page.markdown, doc_id, page.url, page.title)

    indexing = IndexingService(in_memory=True, bm25_dir=tmp_path / "bm25")
    retrieval = RetrievalService(qdrant_store=indexing.qdrant, bm25_store=indexing.bm25)
    assert indexing.chunk_and_index(doc_id=doc_id, blocks=blocks).indexed_count >= 1

    res = retrieval.retrieve(
        SearchQuery(query_text="How many breeding pairs were counted?", top_k=10, top_rerank=3, min_rerank_score=0.15)
    )
    assert not res.refused
    top = res.candidates[0]
    assert "42 breeding pairs" in top.text
    assert top.is_web and top.web_url.startswith(site.base)
