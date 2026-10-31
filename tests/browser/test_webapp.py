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


@pytest.mark.smoke
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


@pytest.mark.smoke
def test_footer_shows_build(page: Page) -> None:
    page.wait_for_function("document.getElementById('footer').textContent.includes('0.1.0')")
    assert "MIT" in (page.text_content("#footer") or "")
    link = page.locator("#footer a")
    assert link.get_attribute("href") == "https://github.com/chris-kuo/fontmerge"


def test_initial_controls(page: Page) -> None:
    assert page.is_disabled("#swap")  # nothing to swap yet
    assert page.is_hidden("#cancel")
    assert page.is_hidden("#western-face-row") and page.is_hidden("#cjk-face-row")
    if not page.evaluate("window.__fontmerge.ready"):
        assert page.is_disabled("#merge")


def test_line_height_choices(page: Page) -> None:
    options = page.locator("#line-height option")
    assert options.evaluate_all("els => els.map(e => e.value)") == [
        "cjk",
        "western",
        "average",
        "max",
    ]
    assert page.input_value("#line-height") == "cjk"
    assert page.text_content("#line-height option[value='average']") == "Average of both"
    page.click("#lang")
    assert page.text_content("#line-height option[value='average']") == "取兩者平均值"


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


@pytest.mark.smoke
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
    ready_page.wait_for_function("window.__fontmerge.preview", timeout=60_000)
    assert ready_page.evaluate("window.__fontmerge.previewMissing") == []
    ready_page.click("#lang")
    tall = ready_page.text_content("li[data-code='tall-glyphs']") or ""
    assert "35 個西文字元高於上緣（940）" in tall and "另有 27 個" in tall

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


# W3: results ------------------------------------------------------------------------------


def _block_pyodide(page: Page) -> None:
    page.route("**/pyodide.mjs", lambda route: route.abort())


def test_runtime_failure_is_explained(browser, site_url: str) -> None:  # type: ignore[no-untyped-def]
    context = browser.new_context(locale="zh-TW")
    page = context.new_page()
    _block_pyodide(page)
    page.goto(site_url)
    page.wait_for_selector("#error-panel:not([hidden])", timeout=60_000)
    assert page.text_content("#error-title") == "無法載入 Python 執行環境"
    assert "cdn.jsdelivr.net" in (page.text_content("#error-hint") or "")
    assert page.is_visible("#retry")
    page.click("#lang")
    assert page.text_content("#error-title") == "The Python runtime could not be loaded"
    context.close()


@pytest.mark.runtime
def test_retry_after_runtime_failure(browser, site_url: str) -> None:  # type: ignore[no-untyped-def]
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    _block_pyodide(page)
    page.goto(site_url)
    page.wait_for_selector("#retry:not([hidden])", timeout=60_000)
    page.unroute("**/pyodide.mjs")
    page.click("#retry")
    assert page.is_hidden("#error-panel")
    page.wait_for_function("window.__fontmerge.ready", timeout=RUNTIME_TIMEOUT_MS)
    context.close()


@pytest.mark.smoke
@pytest.mark.runtime
def test_preview_uses_the_merged_font(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    merge(ready_page)
    ready_page.wait_for_function("window.__fontmerge.preview", timeout=60_000)
    family = ready_page.evaluate("window.__fontmerge.preview.family")
    assert ready_page.evaluate(f"document.fonts.check('20px \"{family}\"')")
    assert family in ready_page.eval_on_selector(
        "#preview-h", "el => getComputedStyle(el).fontFamily"
    )
    assert ready_page.eval_on_selector("#preview-v", "el => getComputedStyle(el).writingMode") == (
        "vertical-rl"
    )
    ready_page.fill("#preview-text", "AB 一 가")  # Hangul is left out by default
    assert ready_page.text_content("#preview-h") == "AB 一 가"
    assert ready_page.text_content("#preview-v") == "AB 一 가"
    assert ready_page.evaluate("window.__fontmerge.previewMissing") == ["가"]
    assert ready_page.locator("#preview-h .missing").count() == 1
    assert ready_page.is_visible("#preview-missing")
    ready_page.fill("#preview-size", "72")
    assert ready_page.eval_on_selector("#preview-h", "el => el.style.fontSize") == "72px"
    ready_page.click("#preview-reset")
    assert "quick brown fox" in ready_page.input_value("#preview-text")


@pytest.mark.runtime
def test_report_is_grouped_and_translated(ready_page: Page, latin_ttf: Path, cjk_otf: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    merge(ready_page)
    warnings = ready_page.locator(".report-group[data-severity='warning']")
    assert "Warnings (" in (warnings.locator("h4").text_content() or "")
    assert warnings.locator("li[data-code='role-coverage']").count() == 1
    notes = ready_page.locator(".report-group[data-severity='info']")
    assert "browser version skips" in (
        notes.locator("li[data-code='ots-skipped']").text_content() or ""
    )
    ready_page.click("#lang")
    role = warnings.locator("li[data-code='role-coverage']").text_content() or ""
    assert "只有 3 個漢字和 2 個假名" in role
    assert "警告（" in (warnings.locator("h4").text_content() or "")


@pytest.mark.runtime
def test_report_download(ready_page: Page, latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    ready_page.fill("#family", "Report Test")
    merge(ready_page)
    with ready_page.expect_download() as info:
        ready_page.click("#download-report")
    assert info.value.suggested_filename == "ReportTest-Regular.report.json"
    path = tmp_path / "r.json"
    info.value.save_as(path)
    data = json.loads(path.read_text())
    assert data["font"] == "ReportTest-Regular.ttf"
    assert any(i["code"] == "role-coverage" for i in data["issues"])


@pytest.mark.smoke
@pytest.mark.runtime
def test_woff2_output(ready_page: Page, latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    pick(ready_page, latin_ttf, cjk_otf)
    ready_page.select_option("#format", "woff2")
    state = merge(ready_page)
    assert state["lastError"] is None, state["lastError"]
    assert state["lastResult"]["filename"].endswith(".woff2")
    assert (ready_page.text_content("#download-format") or "").strip() == "WOFF2"
    with ready_page.expect_download() as info:
        ready_page.click("#download")
    path = tmp_path / info.value.suggested_filename
    info.value.save_as(path)
    assert path.read_bytes()[:4] == b"wOF2"  # WOFF2 signature
    assert TTFont(str(path)).flavor == "woff2"  # decodes (needs brotli on the test side)
    ready_page.wait_for_function("window.__fontmerge.preview", timeout=60_000)


@pytest.mark.runtime
def test_error_title_in_chinese(open_page, cjk_otf: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    page = open_page("zh-TW")
    page.wait_for_function("window.__fontmerge.ready", timeout=RUNTIME_TIMEOUT_MS)
    reserved = build_latin_ttf(
        tmp_path / "Exemplar.ttf",
        family="Exemplar",
        extra_names={"copyright": 'Copyright 2026, with Reserved Font Name "Exemplar".'},
    )
    pick(page, reserved, cjk_otf)
    wait_suggestion(page)
    merge(page)
    assert page.text_content("#error-title") == "設定有問題"
    assert page.is_hidden("#retry")


@pytest.mark.parametrize(("locale", "width"), [("en-US", 1000), ("zh-TW", 375)])
def test_results_layout_fits(  # type: ignore[no-untyped-def]
    browser, site_url: str, latin_ttf: Path, cjk_otf: Path, locale: str, width: int
) -> None:
    """Render a real result through the test hook (no runtime needed) and check layout."""
    result = merge_bytes(latin_ttf.read_bytes(), cjk_otf.read_bytes(), {"naming": {"family": "L"}})
    font = list(result.pop("font"))
    context = browser.new_context(locale=locale, viewport={"width": width, "height": 900})
    page = context.new_page()
    _block_pyodide(page)
    page.goto(site_url)
    page.evaluate(
        "([meta, bytes]) => window.__fontmerge.simulate("
        "{type: 'result', id: 0, meta, font: new Uint8Array(bytes), wasmHeapBytes: null})",
        [result, font],
    )
    page.wait_for_function("window.__fontmerge.preview", timeout=30_000)
    page.fill("#preview-text", "AB 一 " + "長" * 400)  # long text in both previews
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.is_visible(".report-group[data-severity='warning']")
    context.close()
