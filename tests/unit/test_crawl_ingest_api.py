"""IRA-68: adding a web source through the gateway stores a crawled page as the caller's own
markdown document. Uses a real headless browser and a real local web server (skipped without the
`crawl` extra); only the address policy is swapped, because the real one rejects 127.0.0.1."""

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("crawl4ai")

from services.gateway import api  # noqa: E402
from services.ingestion import crawler  # noqa: E402
from services.ingestion.jobs import IngestJobRunner, IngestJobStore  # noqa: E402
from tests.integration.test_crawler import _page, _Server  # noqa: E402
from tests.unit.conftest import TEST_USER  # noqa: E402

client = TestClient(api.app)


class _InlineRunner(IngestJobRunner):
    def submit(self, job, work):
        self._run(job, work)


@pytest.fixture(autouse=True)
def crawl_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # uploads and crawled markdown use relative data/ paths
    monkeypatch.setattr(api.settings.ingestion, "crawler", "crawl4ai")
    store = IngestJobStore(lambda: None)
    monkeypatch.setattr(api, "ingest_jobs", store)
    monkeypatch.setattr(api, "ingest_runner", _InlineRunner(store))
    indexed = []
    monkeypatch.setattr(api, "_index_owned", lambda doc_id, blocks, user: indexed.append((doc_id, len(blocks))))
    monkeypatch.setattr(crawler, "check_public_url", lambda url: None)  # the test server is on 127.0.0.1
    return indexed


@pytest.fixture
def site():
    routes: dict[str, str] = {}
    server = _Server(routes)
    routes.update({
        "/": _page("Falcon Census", '<h1>Falcon Census</h1><p>42 breeding pairs.</p><a href="/diet">Diet</a>'),
        "/diet": _page("Diet", "<h1>Diet</h1><p>Falcons hunt pigeons.</p>"),
    })
    yield server
    server.stop()


def test_sync_route_stores_a_crawled_page_as_an_owned_markdown_doc(site, identity):
    r = client.post("/api/v1/ingest/url", json={"url": f"{site.base}/"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"].startswith("web_crawl_") and not body["doc_id"].startswith("web_wiki_index")
    assert any("42 breeding pairs" in b["text"] for b in body["blocks"])
    assert all(b["meta"]["is_web"] and b["meta"]["web_url"] == f"{site.base}/" for b in body["blocks"])
    assert body["doc_id"] in identity.owned_doc_ids(TEST_USER.id)

    raw = client.get(f"/api/v1/documents/{body['doc_id']}/raw")
    assert raw.status_code == 200 and raw.headers["content-type"].startswith("text/markdown")
    assert "42 breeding pairs" in raw.text
    assert client.get("/api/v1/preview", params={"doc_id": body["doc_id"]}).status_code == 404

    listed = {d["doc_id"]: d for d in client.get("/api/v1/documents").json()["documents"]}
    assert listed[body["doc_id"]]["is_web"] is True


def test_url_job_with_depth_attaches_every_page(site, make_project, crawl_enabled):
    project = make_project()
    r = client.post(
        "/api/v1/ingest/jobs/url",
        json={"url": f"{site.base}/", "session_id": project.id, "max_depth": 1, "max_pages": 5},
    )
    assert r.status_code == 202, r.text
    (job,) = client.get("/api/v1/ingest/jobs", params={"session_id": project.id}).json()["jobs"]
    assert job["status"] == "done", job
    files = api.session_manager.get_session(project.id)[0].files
    assert len(files) == 2 and all(f.startswith("web_crawl_") for f in files)
    assert len(crawl_enabled) == 2  # both pages were indexed


def test_private_start_url_is_refused_without_launching_a_browser(monkeypatch):
    monkeypatch.undo()  # real address policy again
    monkeypatch.setattr(api.settings.ingestion, "crawler", "crawl4ai")
    r = client.post("/api/v1/ingest/url", json={"url": "http://127.0.0.1:6333/"})
    assert r.status_code == 422 and "publicly reachable" in r.json()["detail"]


def test_missing_engine_falls_back_to_the_pdf_fetch(monkeypatch, site):
    monkeypatch.setattr(crawler, "available", lambda: False)
    seen = {}

    def fake_pdf(url, **kw):
        seen["url"] = url
        raise api.UrlSourceError("stop here")

    monkeypatch.setattr(api, "url_to_pdf", fake_pdf)
    assert client.post("/api/v1/ingest/url", json={"url": f"{site.base}/"}).status_code == 422
    assert seen["url"] == f"{site.base}/"


def test_pdf_links_keep_the_pdf_path(monkeypatch, site):
    seen = {}

    def fake_pdf(url, **kw):
        seen["url"] = url
        raise api.UrlSourceError("stop here")

    monkeypatch.setattr(api, "url_to_pdf", fake_pdf)
    client.post("/api/v1/ingest/url", json={"url": f"{site.base}/paper.pdf"})
    assert seen["url"].endswith("/paper.pdf")

