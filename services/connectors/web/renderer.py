"""Headless-browser rendering for JavaScript sites (IRA-57), via Playwright + Chromium.

Optional: if Playwright isn't installed the connector still works on static HTML and reports such pages
as `needs_js`. Every request the browser makes (scripts, XHR, iframes, redirects) goes through the same
public-address check as static fetches, so a page can't use the browser to reach internal services.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from services.common.logger import get_logger
from services.ingestion.url_source import UrlSourceError, check_public_url

logger = get_logger("connectors.web.renderer")

_BLOCKED_RESOURCES = {"image", "media", "font"}


def browser_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=512)
def _host_is_public(scheme: str, host: str) -> bool:
    try:
        check_public_url(f"{scheme}://{host}/")
        return True
    except UrlSourceError:
        return False


def _allowed(url: str) -> bool:
    p = urlparse(url)
    if p.scheme in ("data", "blob", "about"):
        return True
    return p.scheme in ("http", "https") and bool(p.hostname) and _host_is_public(p.scheme, p.hostname)


def render(url: str, *, timeout_s: float, user_agent: str) -> tuple[str, str]:
    """Loads `url` in headless Chromium and returns (final_url, html after scripts ran)."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    if not _allowed(url):
        raise UrlSourceError("That address isn't publicly reachable, so it can't be added.")
    timeout_ms = int(timeout_s * 1000)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        try:
            context = browser.new_context(user_agent=user_agent, java_script_enabled=True, service_workers="block")

            def guard(route) -> None:
                req = route.request
                if req.resource_type in _BLOCKED_RESOURCES or not _allowed(req.url):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", guard)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
                except PlaywrightError:
                    pass  # long-polling sites never go idle; the DOM is usually ready by now
                final_url = page.url
                if not _allowed(final_url):
                    raise UrlSourceError("The page redirected to an address that isn't publicly reachable.")
                return final_url, page.content()
            except PlaywrightError as exc:
                raise UrlSourceError(f"The browser couldn't load the page: {str(exc).splitlines()[0][:160]}") from exc
        finally:
            browser.close()
