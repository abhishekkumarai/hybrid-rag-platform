"""Web sources: SSRF guard, HTML -> PDF conversion, and the /api/v1/ingest/url endpoint."""

import socket
from unittest.mock import MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from services.gateway import api
from services.ingestion import url_source
from services.ingestion.url_source import (
    UrlSourceError,
    check_public_url,
    fetch_public_url,
    html_to_pdf,
)
from tests.unit.conftest import TEST_USER

client = TestClient(api.app)
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:6333/collections",
    "http://10.1.2.3/",
    "http://192.168.1.10/",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://user:pw@example.com/",
])
def test_non_public_or_non_http_urls_are_refused(url):
    with pytest.raises(UrlSourceError):
        check_public_url(url)


def test_hostname_resolving_to_a_private_address_is_refused():
    private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 80))]
    with patch.object(url_source.socket, "getaddrinfo", return_value=private):
        with pytest.raises(UrlSourceError):
            check_public_url("http://innocent-looking.example/")


def _resp(status, headers=None, body=b""):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.is_redirect = status in (301, 302, 303, 307, 308)
    r.iter_content.return_value = [body]
    r.raw._connection.sock.getpeername.return_value = ("93.184.216.34", 443)
    r.__enter__.return_value = r
    r.__exit__.return_value = False
    return r


def test_redirect_to_an_internal_address_is_refused():
    hop = _resp(302, {"location": "http://127.0.0.1:6379/"})
    real = socket.getaddrinfo

    def resolve(host, *a, **k):
        return PUBLIC if host == "example.com" else real(host, *a, **k)

    with patch.object(url_source.socket, "getaddrinfo", side_effect=resolve), \
         patch.object(url_source.requests, "get", return_value=hop):
        with pytest.raises(UrlSourceError, match="publicly reachable"):
            fetch_public_url("https://example.com/", max_bytes=10_000, timeout_s=1, max_redirects=3)


def test_connected_peer_is_rechecked_against_dns_rebinding():
    rebound = _resp(200, {"content-type": "text/html"}, b"<p>x</p>")
    rebound.raw._connection.sock.getpeername.return_value = ("127.0.0.1", 80)
    with patch.object(url_source.socket, "getaddrinfo", return_value=PUBLIC), \
         patch.object(url_source.requests, "get", return_value=rebound):
        with pytest.raises(UrlSourceError):
            fetch_public_url("http://example.com/", max_bytes=10_000, timeout_s=1, max_redirects=3)


def test_oversized_pages_are_refused():
    big = _resp(200, {"content-type": "text/html"}, b"x" * 2048)
    with patch.object(url_source.socket, "getaddrinfo", return_value=PUBLIC), \
         patch.object(url_source.requests, "get", return_value=big):
        with pytest.raises(UrlSourceError, match="larger"):
            fetch_public_url("http://example.com/", max_bytes=1024, timeout_s=1, max_redirects=3)


def test_html_becomes_a_pdf_with_readable_text_and_no_chrome():
    title, pdf = html_to_pdf(
        "<html><head><title>Falcon <b>&amp;</b> Co</title><script>steal()</script></head><body>"
        "<nav>site menu</nav><main><h1>Falcon</h1><p>The Falcon cluster has 48 GB.</p></main></body></html>",
        "https://example.com/falcon",
    )
    text = fitz.open("pdf", pdf)[0].get_text()
    assert "48 GB" in text and "Source: https://example.com/falcon" in text
    assert "steal" not in text and "site menu" not in text
    assert title


def test_ingest_url_endpoint_records_ownership_like_an_upload(identity, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, pdf = html_to_pdf("<main><h1>Falcon</h1><p>The Falcon cluster has 48 GB of memory.</p></main>",
                         "https://example.com/falcon")
    with patch.object(api, "url_to_pdf", return_value=("example_com_falcon.pdf", pdf)):
        r = client.post("/api/v1/ingest/url", json={"url": "https://example.com/falcon"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"].startswith("example_com_falcon_") and body["blocks"]
    assert any("48 GB" in b["text"] for b in body["blocks"])
    assert body["doc_id"] in identity.owned_doc_ids(TEST_USER.id)


def test_ingest_url_endpoint_reports_unfetchable_urls_as_422():
    r = client.post("/api/v1/ingest/url", json={"url": "http://127.0.0.1:6333/"})
    assert r.status_code == 422
    assert "publicly reachable" in r.json()["detail"]
