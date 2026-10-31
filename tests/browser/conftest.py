"""Browser tests for the web app (Playwright + headless Chromium).

Skipped unless FONTMERGE_BROWSER=1. Tests marked ``runtime`` need to download Pyodide
from the CDN, so they run in GitHub Actions; the others run anywhere Chromium does.

Environment:
  FONTMERGE_SITE      a prebuilt site folder to serve (default: build one)
  FONTMERGE_SITE_URL  test an already running site instead, e.g. the live GitHub Pages URL
  FONTMERGE_ENGINE    chromium (default), firefox or webkit
"""

from __future__ import annotations

import importlib.util
import os
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

if os.environ.get("FONTMERGE_BROWSER") != "1":
    pytest.skip("browser tests need FONTMERGE_BROWSER=1", allow_module_level=True)

from playwright.sync_api import Browser, Page, sync_playwright  # noqa: E402

RUNTIME_TIMEOUT_MS = 5 * 60 * 1000  # first Pyodide download + package load
MERGE_TIMEOUT_MS = 15 * 60 * 1000  # a large CJK merge in WebAssembly


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "runtime: needs Pyodide from the CDN")
    config.addinivalue_line("markers", "smoke: quick check of a deployed site")


@pytest.fixture(scope="session")
def site_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    prebuilt = os.environ.get("FONTMERGE_SITE")
    if prebuilt:
        return Path(prebuilt)
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Path(module.build_site(tmp_path_factory.mktemp("site") / "site"))


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="session")
def site_url(request: pytest.FixtureRequest) -> Iterator[str]:
    live = os.environ.get("FONTMERGE_SITE_URL")
    if live:
        yield live if live.endswith("/") else live + "/"
        return
    site_dir: Path = request.getfixturevalue("site_dir")
    handler = partial(_QuietHandler, directory=str(site_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        engine = os.environ.get("FONTMERGE_ENGINE", "chromium")
        b = getattr(p, engine).launch()
        yield b
        b.close()


def _open(browser: Browser, url: str, locale: str) -> tuple[Page, list[str]]:
    context = browser.new_context(locale=locale, accept_downloads=True)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(url)
    return page, errors


@pytest.fixture
def page(browser: Browser, site_url: str) -> Iterator[Page]:
    p, errors = _open(browser, site_url, "en-US")
    yield p
    p.context.close()
    assert not errors, f"JavaScript errors: {errors}"


@pytest.fixture
def open_page(browser: Browser, site_url: str) -> Iterator[Any]:
    """Factory: open the app with a given browser locale."""
    opened: list[tuple[Page, list[str]]] = []

    def factory(locale: str = "en-US") -> Page:
        p, errors = _open(browser, site_url, locale)
        opened.append((p, errors))
        return p

    yield factory
    for p, errors in opened:
        p.context.close()
        assert not errors, f"JavaScript errors: {errors}"


@pytest.fixture
def ready_page(page: Page) -> Page:
    """The app with Pyodide and fontmerge loaded."""
    page.wait_for_function(
        "window.__fontmerge.ready || document.getElementById('status').dataset.state === 'error'",
        timeout=RUNTIME_TIMEOUT_MS,
    )
    if not page.evaluate("window.__fontmerge.ready"):
        message = page.text_content("#error-message")
        pytest.fail(f"the Python runtime did not load: {message}")
    return page
