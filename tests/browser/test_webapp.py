"""W1: the web app in a real browser."""

from __future__ import annotations

import json
import os
import time
from io import BytesIO
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont
from playwright.sync_api import Page

from fontmerge.web import merge_bytes

from .conftest import MERGE_TIMEOUT_MS

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "tests" / "realfonts"


# Page and language (no Python runtime needed) -------------------------------------------


def test_page_loads_in_english(page: Page) -> None:
    assert page.title() == "fontmerge"
    assert page.text_content("h1") == "fontmerge"
    assert "never uploaded" in (page.text_content(".privacy") or "")
    assert page.input_value("#family") == "Merged"
    assert page.eval_on_selector("#format", "el => el.value") == "ttf"  # TTF by default
    assert page.get_attribute("html", "lang") == "en"


def test_chinese_browser_gets_chinese(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    assert page.get_attribute("html", "lang") == "zh-Hant"
    assert page.text_content(".privacy") == "字型只在你的裝置上處理，不會上傳。"
    assert page.text_content("#merge") == "合併字型"
    assert page.text_content("#lang") == "English"


def test_language_toggle_is_remembered(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("en-US")
    page.click("#lang")
    assert page.text_content("#merge") == "合併字型"
    assert page.text_content("#status")  # status re-translated, never empty
    page.reload()
    assert page.text_content("#merge") == "合併字型"  # kept in localStorage
    page.click("#lang")
    assert page.text_content("#merge") == "Merge fonts"


def test_footer_shows_build(page: Page) -> None:
    page.wait_for_function("document.getElementById('footer').textContent.includes('0.1.0')")
    assert "MIT" in (page.text_content("#footer") or "")


def test_merge_button_waits_for_runtime(page: Page) -> None:
    if not page.evaluate("window.__fontmerge.ready"):
        assert page.is_disabled("#merge")


def test_narrow_screen_has_no_horizontal_scroll(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("en-US")
    page.set_viewport_size({"width": 375, "height": 800})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# Merging (needs Pyodide) ------------------------------------------------------------------


def run_merge(page: Page, western: Path, cjk: Path, **fields: str) -> dict:  # type: ignore[type-arg]
    page.set_input_files("#western", str(western))
    page.set_input_files("#cjk", str(cjk))
    for selector, value in fields.items():
        if selector == "line_height":
            page.select_option("#line-height", value)
        else:
            page.fill(f"#{selector.replace('_', '-')}", value)
    page.click("#merge")
    page.wait_for_function(
        "window.__fontmerge.lastResult || window.__fontmerge.lastError", timeout=MERGE_TIMEOUT_MS
    )
    return page.evaluate("window.__fontmerge")  # type: ignore[no-any-return]


def download(page: Page, tmp_path: Path) -> TTFont:
    with page.expect_download() as info:
        page.click("#download")
    path = tmp_path / info.value.suggested_filename
    info.value.save_as(path)
    return TTFont(str(path))


def assert_same_font(a: TTFont, b: TTFont) -> None:
    assert a.getGlyphOrder() == b.getGlyphOrder()
    assert a.getBestCmap() == b.getBestCmap()
    assert a["hmtx"].metrics == b["hmtx"].metrics
    assert a["OS/2"].sTypoAscender == b["OS/2"].sTypoAscender
    assert a["name"].getDebugName(4) == b["name"].getDebugName(4)


@pytest.mark.runtime
def test_merge_matches_python(
    ready_page: Page, latin_ttf: Path, cjk_otf: Path, tmp_path: Path
) -> None:
    state = run_merge(ready_page, latin_ttf, cjk_otf, family="Browser Test", style="Light")
    assert state["lastError"] is None, state["lastError"]
    result = state["lastResult"]
    assert result["filename"] == "BrowserTest-Light.ttf"
    browser_font = download(ready_page, tmp_path)
    expected = merge_bytes(
        latin_ttf.read_bytes(),
        cjk_otf.read_bytes(),
        {"naming": {"family": "Browser Test", "style": "Light"}, "metrics": {"line_height": "cjk"}},
    )
    assert_same_font(browser_font, TTFont(BytesIO(expected["font"])))
    assert ready_page.get_attribute("#status", "data-state") == "done"
    assert ready_page.locator("#progress li").count() >= 10


@pytest.mark.runtime
def test_error_shows_message_and_hint(ready_page: Page, latin_ttf: Path, cjk_ttc: Path) -> None:
    state = run_merge(ready_page, latin_ttf, cjk_ttc)
    assert state["lastResult"] is None
    assert "2 faces" in state["lastError"]["message"]
    assert ready_page.is_visible("#error-panel")
    assert "--cjk-face" in (ready_page.text_content("#error-hint") or "")
    assert ready_page.is_enabled("#merge")  # can try again


@pytest.mark.runtime
def test_collection_face_from_form(ready_page: Page, latin_ttf: Path, cjk_ttc: Path) -> None:
    state = run_merge(ready_page, latin_ttf, cjk_ttc, cjk_face="1")
    assert state["lastError"] is None, state["lastError"]


@pytest.mark.runtime
def test_progress_in_chinese(open_page, latin_ttf: Path, cjk_otf: Path) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    page.wait_for_function("window.__fontmerge.ready", timeout=5 * 60 * 1000)
    run_merge(page, latin_ttf, cjk_otf)
    steps = page.locator("#progress li").all_text_contents()
    assert any("載入字型" in s for s in steps) and any("完成" in s for s in steps)
    assert "完成" in (page.text_content("#status") or "")


@pytest.mark.runtime
@pytest.mark.realfont
def test_real_merge_benchmark(ready_page: Page, tmp_path: Path) -> None:
    """Literata Light + Iansui: same font as the CLI, plus time and memory."""
    started = time.monotonic()
    state = run_merge(
        ready_page,
        REAL / "Literata-Light.ttf",
        REAL / "Iansui-Regular.ttf",
        family="Iansui Literata",
        style="Light",
        scale="0.96",
    )
    wall = time.monotonic() - started
    assert state["lastError"] is None, state["lastError"]
    result = state["lastResult"]
    assert result["coverage"] == {"western": 1147, "cjk": 12154}

    browser_font = download(ready_page, tmp_path)
    expected = merge_bytes(
        (REAL / "Literata-Light.ttf").read_bytes(),
        (REAL / "Iansui-Regular.ttf").read_bytes(),
        {
            "naming": {"family": "Iansui Literata", "style": "Light"},
            "normalize": {"western_scale": 0.96},
            "metrics": {"line_height": "cjk"},
        },
    )
    assert_same_font(browser_font, TTFont(BytesIO(expected["font"])))

    bench = {
        "merge_seconds_in_browser": result["seconds"],
        "wall_seconds_incl_file_transfer": round(wall, 1),
        "native_seconds": expected["seconds"],
        "wasm_heap_mb": round(result["wasmHeapBytes"] / 1048576)
        if result["wasmHeapBytes"]
        else None,
        "output_mb": round(result["bytes"] / 1048576, 1),
        "glyphs": result["glyphs"],
    }
    print("BENCHMARK", json.dumps(bench))
    out = os.environ.get("FONTMERGE_BENCH_OUT")
    if out:
        Path(out).write_text(json.dumps(bench, indent=2), encoding="utf-8")
