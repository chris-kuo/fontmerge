"""The web app in a real browser (W1 proof of concept, W2 inputs and settings)."""

from __future__ import annotations

import json
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fontTools.ttLib import TTFont
from playwright.sync_api import Page

from fontfactory import build_latin_ttf
from fontmerge.web import merge_bytes

from .conftest import MERGE_TIMEOUT_MS, RUNTIME_TIMEOUT_MS

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "tests" / "realfonts"
INSPECT_TIMEOUT_MS = 120_000


# Page and language (no Python runtime needed) -------------------------------------------


def test_page_loads_in_english(page: Page) -> None:
    assert page.title() == "fontmerge"
    assert "never uploaded" in (page.text_content(".privacy") or "")
    assert page.input_value("#family") == "Merged"
    assert page.eval_on_selector("#format", "el => el.value") == "ttf"  # TTF by default
    assert page.get_attribute("html", "lang") == "en"
    assert "Drop a font here" in (page.text_content("#western-name") or "")


def test_chinese_browser_gets_chinese(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    assert page.get_attribute("html", "lang") == "zh-Hant"
    assert page.text_content(".privacy") == "字型只在你的裝置上處理，不會上傳。"
    assert page.text_content("#merge") == "合併字型"
    assert "拖放" in (page.text_content("#cjk-name") or "")
    assert page.get_attribute("#swap", "title") == "交換兩個字型"


def test_language_toggle_is_remembered(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("en-US")
    page.click("#lang")
    assert page.text_content("#merge") == "合併字型"
    page.reload()
    assert page.text_content("#merge") == "合併字型"  # kept in localStorage
    page.click("#lang")
    assert page.text_content("#merge") == "Merge fonts"


def test_footer_shows_build(page: Page) -> None:
    page.wait_for_function("document.getElementById('footer').textContent.includes('0.1.0')")
    assert "MIT" in (page.text_content("#footer") or "")


def test_initial_controls(page: Page) -> None:
    assert page.is_disabled("#swap")  # nothing to swap yet
    assert page.is_hidden("#cancel")
    assert page.is_hidden("#western-face-row") and page.is_hidden("#cjk-face-row")
    if not page.evaluate("window.__fontmerge.ready"):
        assert page.is_disabled("#merge")


def test_more_settings(page: Page) -> None:
    assert page.is_hidden("#punctuation")
    page.click(".more summary")
    assert page.is_visible("#punctuation")
    assert page.eval_on_selector("#fallback", "el => el.checked")
    assert page.input_value("#font-version") == "1.000"


def test_narrow_screen_has_no_horizontal_scroll(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("en-US")
    page.set_viewport_size({"width": 375, "height": 800})
    page.click(".more summary")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


# Helpers for tests that need the Python runtime -----------------------------------------


def pick(page: Page, western: Path | None = None, cjk: Path | None = None) -> None:
    """Choose fonts and wait until each is inspected."""
    for role, path in (("western", western), ("cjk", cjk)):
        if path is None:
            continue
        page.set_input_files(f"#{role}", str(path))
        page.wait_for_function(
            f"window.__fontmerge.info.{role} && window.__fontmerge.info.{role}.profile",
            timeout=INSPECT_TIMEOUT_MS,
        )


def wait_suggestion(page: Page) -> dict[str, Any]:
    page.wait_for_function("window.__fontmerge.suggestion", timeout=INSPECT_TIMEOUT_MS)
    return page.evaluate("window.__fontmerge.suggestion")  # type: ignore[no-any-return]


def merge(page: Page) -> dict[str, Any]:
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


# W1: merging ------------------------------------------------------------------------------


@pytest.mark.runtime
def test_merge_matches_python(
    ready_page: Page, latin_ttf: Path, cjk_otf: Path, tmp_path: Path
) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    wait_suggestion(ready_page)
    ready_page.fill("#family", "Browser Test")
    ready_page.fill("#style", "Light")
    scale = float(ready_page.input_value("#scale"))
    state = merge(ready_page)
    assert state["lastError"] is None, state["lastError"]
    assert state["lastResult"]["filename"] == "BrowserTest-Light.ttf"
    expected = merge_bytes(
        latin_ttf.read_bytes(),
        cjk_otf.read_bytes(),
        {
            "naming": {"family": "Browser Test", "style": "Light"},
            "normalize": {"western_scale": scale},
        },
    )
    assert_same_font(download(ready_page, tmp_path), TTFont(BytesIO(expected["font"])))
    assert ready_page.get_attribute("#status", "data-state") == "done"
    assert ready_page.locator("#progress li").count() >= 10
    assert ready_page.is_hidden("#cancel") and ready_page.is_hidden("#bar")


@pytest.mark.runtime
def test_progress_in_chinese(open_page, latin_ttf: Path, cjk_otf: Path) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    page.wait_for_function("window.__fontmerge.ready", timeout=RUNTIME_TIMEOUT_MS)
    pick(page, latin_ttf, cjk_otf)
    merge(page)
    steps = page.locator("#progress li").all_text_contents()
    assert any("載入字型" in s for s in steps) and any("完成" in s for s in steps)
    assert "完成" in (page.text_content("#status") or "")


# W2: inputs and settings ------------------------------------------------------------------


@pytest.mark.runtime
def test_summaries_and_suggestion(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    suggestion = wait_suggestion(ready_page)
    western = ready_page.text_content("#western-summary") or ""
    assert "Test Latin" in western and "Latin" in western and "TrueType" in western
    cjk = ready_page.text_content("#cjk-summary") or ""
    assert "Test CJK" in cjk and "CFF" in cjk
    assert "Han characters" in cjk  # the tiny CJK test font is flagged
    assert ready_page.input_value("#family") == "Test CJK Test Latin" == suggestion["family"]
    assert ready_page.input_value("#scale") == f"{suggestion['scale']:.2f}"
    assert ready_page.is_visible("#suggested")
    assert ready_page.is_enabled("#swap")


@pytest.mark.runtime
def test_edited_fields_are_kept(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    ready_page.fill("#family", "My Own Name")
    pick(ready_page, latin_ttf, cjk_otf)
    wait_suggestion(ready_page)
    assert ready_page.input_value("#family") == "My Own Name"
    assert ready_page.input_value("#style") == "Regular"  # suggested (not edited)


@pytest.mark.runtime
def test_collection_face_menu(ready_page: Page, latin_ttf: Path, cjk_ttc: Path) -> None:
    pick(ready_page, latin_ttf, cjk_ttc)
    assert ready_page.is_visible("#cjk-face-row")
    assert ready_page.locator("#cjk-face option").all_text_contents() == [
        "0: Test CJK SC Regular",
        "1: Test CJK JP Regular",
    ]
    assert "Test CJK SC" in (ready_page.text_content("#cjk-summary") or "")
    ready_page.select_option("#cjk-face", "1")
    ready_page.wait_for_function(
        "document.getElementById('cjk-summary').textContent.includes('Test CJK JP')",
        timeout=INSPECT_TIMEOUT_MS,
    )
    state = merge(ready_page)
    assert state["lastError"] is None, state["lastError"]
    assert "Test CJK JP" in json.dumps(state["lastResult"]["issues"])


@pytest.mark.runtime
def test_swap(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, western=cjk_otf, cjk=latin_ttf)  # the wrong way round
    assert "basic Latin letters" in (ready_page.text_content("#western-summary") or "")
    ready_page.click("#swap")
    assert "TestLatin" in (ready_page.text_content("#western-name") or "")
    assert "TestCJK" in (ready_page.text_content("#cjk-name") or "")
    ready_page.wait_for_function(
        "document.getElementById('family').value === 'Test CJK Test Latin'",
        timeout=INSPECT_TIMEOUT_MS,
    )
    assert "basic Latin" not in (ready_page.text_content("#western-summary") or "")


@pytest.mark.runtime
def test_reserved_name_warning_and_error(ready_page: Page, cjk_otf: Path, tmp_path: Path) -> None:
    reserved = build_latin_ttf(
        tmp_path / "Exemplar.ttf",
        family="Exemplar",
        extra_names={"copyright": 'Copyright 2026, with Reserved Font Name "Exemplar".'},
    )
    pick(ready_page, reserved, cjk_otf)
    wait_suggestion(ready_page)
    assert ready_page.is_visible("#rfn-warning")  # the suggested name contains "Exemplar"
    ready_page.fill("#family", "Something Else")
    assert ready_page.is_hidden("#rfn-warning")
    ready_page.fill("#family", "exemplar merged")
    assert ready_page.is_visible("#rfn-warning")
    state = merge(ready_page)
    assert "Reserved Font Name" in state["lastError"]["message"]
    assert "family name without it" in (ready_page.text_content("#error-hint") or "")
    assert ready_page.is_enabled("#merge")  # can try again


@pytest.mark.runtime
def test_more_settings_reach_the_merge(
    ready_page: Page, latin_ttf: Path, cjk_otf: Path, tmp_path: Path
) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    wait_suggestion(ready_page)
    ready_page.click(".more summary")
    ready_page.select_option("#punctuation", "cjk")
    ready_page.fill("#overrides", "U+0041=cjk")
    ready_page.fill("#font-version", "2.500")
    ready_page.fill("#vendor", "ABCD")
    state = merge(ready_page)
    assert state["lastError"] is None, state["lastError"]
    font = download(ready_page, tmp_path)
    cmap = font.getBestCmap()
    assert font["hmtx"][cmap[0x41]][0] == 650  # the CJK test font's 'A'
    assert font["hmtx"][cmap[0x2026]][0] == 1000  # the CJK font's ellipsis
    assert font["name"].getDebugName(5) == "Version 2.500"
    assert font["OS/2"].achVendID == "ABCD"


@pytest.mark.runtime
def test_strict_mode_refuses_warnings(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    ready_page.click(".more summary")
    ready_page.check("#strict")
    state = merge(ready_page)
    assert "role-coverage" in state["lastError"]["message"]


@pytest.mark.runtime
def test_unreadable_file(ready_page: Page, tmp_path: Path) -> None:
    junk = tmp_path / "junk.ttf"
    junk.write_bytes(b"not a font" * 100)
    ready_page.set_input_files("#western", str(junk))
    ready_page.wait_for_selector("#western-summary .summary-error", timeout=INSPECT_TIMEOUT_MS)
    assert "could not read" in (ready_page.text_content("#western-summary") or "")


@pytest.mark.runtime
@pytest.mark.realfont
def test_cancel_and_merge_again(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, REAL / "Literata-Light.ttf", REAL / "Iansui-Regular.ttf")
    ready_page.click("#merge")
    assert ready_page.is_visible("#cancel")
    ready_page.wait_for_function(
        "document.querySelectorAll('#progress li').length >= 3", timeout=MERGE_TIMEOUT_MS
    )
    ready_page.click("#cancel")
    assert ready_page.get_attribute("#status", "data-key") == "statusCancelled"
    assert ready_page.is_hidden("#cancel")
    ready_page.wait_for_function("window.__fontmerge.ready", timeout=RUNTIME_TIMEOUT_MS)
    pick(ready_page, latin_ttf, cjk_otf)
    state = merge(ready_page)
    assert state["lastError"] is None and state["lastResult"], state["lastError"]


@pytest.mark.runtime
@pytest.mark.realfont
def test_real_merge_benchmark(ready_page: Page, tmp_path: Path) -> None:
    """Literata Light + Iansui with the page's own suggestions; time and memory."""
    pick(ready_page, REAL / "Literata-Light.ttf", REAL / "Iansui-Regular.ttf")
    suggestion = wait_suggestion(ready_page)
    # The page suggests exactly the setup chosen for this pair.
    assert ready_page.input_value("#family") == "Iansui Literata"
    assert ready_page.input_value("#style") == "Light"
    assert ready_page.input_value("#scale") == "0.96"
    assert suggestion["reserved_conflicts"] == []
    started = time.monotonic()
    state = merge(ready_page)
    wall = time.monotonic() - started
    assert state["lastError"] is None, state["lastError"]
    result = state["lastResult"]
    assert result["coverage"] == {"western": 1147, "cjk": 12154}

    expected = merge_bytes(
        (REAL / "Literata-Light.ttf").read_bytes(),
        (REAL / "Iansui-Regular.ttf").read_bytes(),
        {
            "naming": {"family": "Iansui Literata", "style": "Light"},
            "normalize": {"western_scale": 0.96},
        },
    )
    assert_same_font(download(ready_page, tmp_path), TTFont(BytesIO(expected["font"])))

    bench = {
        "merge_seconds_in_browser": result["seconds"],
        "wall_seconds_incl_file_transfer": round(wall, 1),
        "native_seconds": expected["seconds"],
        "wasm_heap_mb": round((result["wasmHeapBytes"] or 0) / 1048576) or None,
        "output_mb": round(result["bytes"] / 1048576, 1),
        "glyphs": result["glyphs"],
    }
    print("BENCHMARK", json.dumps(bench))
    out = os.environ.get("FONTMERGE_BENCH_OUT")
    if out:
        Path(out).write_text(json.dumps(bench, indent=2), encoding="utf-8")


def test_long_error_text_wraps_on_phones(open_page) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    page.set_viewport_size({"width": 390, "height": 800})
    page.evaluate(
        "() => { const p = document.getElementById('error-panel'); p.hidden = false;"
        " document.getElementById('error-message').textContent ="
        " 'https://example.com/' + 'x'.repeat(200); }"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
