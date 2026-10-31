"""Stage 5: Metadata Builder."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
from fontTools.ttLib import TTFont

from fontmerge.errors import ConfigError
from fontmerge.inspector import inspect_font
from fontmerge.loader import load_font
from fontmerge.merge import merge_fonts
from fontmerge.metadata import (
    build_metadata,
    check_reserved_names,
    glyph_extents,
    line_metrics,
    postscript_name,
    strictest_fs_type,
    style_names,
    weight_class,
)
from fontmerge.models import (
    FontProfile,
    LicenseInfo,
    MetricsConfig,
    NamingConfig,
    NormalizePlan,
    RoutingConfig,
)
from fontmerge.normalize import normalize
from fontmerge.router import build_plan
from fontmerge.subset import subset_pair

USE_TYPO = 1 << 7
REGULAR = 1 << 6


@pytest.fixture
def merged(latin_ttf: Path, cjk_otf: Path) -> dict[str, Any]:
    w_src, c_src = load_font(latin_ttf), load_font(cjk_otf)
    w_prof, c_prof = inspect_font(w_src), inspect_font(c_src)
    route = build_plan(w_prof, c_prof, RoutingConfig())
    w, c = subset_pair(w_src, c_src, route)
    plan = NormalizePlan(
        target_upm=1000, target_outline="glyf", vertical_advance=1000, vertical_top=880
    )
    w, c = normalize(w, c, plan)
    return {"font": merge_fonts(w, c), "w": w_prof, "c": c_prof, "plan": plan}


def build(m: dict[str, Any], style: str = "Light", **kw: Any) -> TTFont:
    naming = NamingConfig(family="Test Merged", style=style)
    return build_metadata(m["font"], m["w"], m["c"], naming, kw.get("metrics"), m["plan"])


def with_license(p: FontProfile, **kw: Any) -> FontProfile:
    return dataclasses.replace(p, license=dataclasses.replace(p.license, **kw))


# Pure helpers ---------------------------------------------------------------------------


def test_style_names_ribbi() -> None:
    assert style_names(NamingConfig(family="F", style="Bold")) == {1: "F", 2: "Bold"}


def test_style_names_non_ribbi() -> None:
    assert style_names(NamingConfig(family="F", style="Light")) == {
        1: "F Light",
        2: "Regular",
        16: "F",
        17: "Light",
    }


def test_postscript_name() -> None:
    assert postscript_name(NamingConfig(family="Iansui Literata", style="Light")) == (
        "IansuiLiterata-Light"
    )
    assert postscript_name(NamingConfig(family="Ünï (Test)", style="Semi Bold")) == "nTest-SemiBold"


@pytest.mark.parametrize(
    ("style", "weight"),
    [("Light", 300), ("Regular", 400), ("Bold", 700), ("Semi Bold", 600), ("Light Italic", 300)],
)
def test_weight_class(style: str, weight: int) -> None:
    assert weight_class(style) == weight


def test_weight_class_unknown() -> None:
    assert weight_class("Wobbly") is None


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        ((0, 0), 0),
        ((0, 8), 8),
        ((8, 4), 4),
        ((4, 2), 2),
        ((0, 0x0108), 0x0108),
        ((0x0200, 8), 0x0208),
    ],
)
def test_strictest_fs_type(inputs: tuple[int, int], expected: int) -> None:
    assert strictest_fs_type(*inputs) == expected


def test_reserved_names_enforced(latin_ttf: Path) -> None:
    p = with_license(inspect_font(load_font(latin_ttf)), reserved_font_names=("Literata",))
    with pytest.raises(ConfigError, match="Reserved Font Name"):
        check_reserved_names(NamingConfig(family="Iansui Literata"), p)
    with pytest.raises(ConfigError):
        check_reserved_names(NamingConfig(family="IansuiLITERATA"), p)
    check_reserved_names(NamingConfig(family="Iansui Serif"), p)


def test_line_metrics_modes(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = inspect_font(load_font(latin_ttf)), inspect_font(load_font(cjk_otf))
    assert line_metrics(w, c, "cjk", 1000) == (880, -120, 0)
    w_scaled = line_metrics(w, c, "western", 1000, 0.5)
    assert w_scaled == (round(1900 * 1000 / 2048 * 0.5), round(-500 * 1000 / 2048 * 0.5), 0)
    biggest = line_metrics(w, c, "max", 1000)
    assert biggest == (round(1900 * 1000 / 2048), -244, 0)


# build_metadata on generated fonts ------------------------------------------------------


def test_names_written(merged: dict[str, Any]) -> None:
    name = build(merged)["name"]
    assert name.getDebugName(1) == "Test Merged Light"
    assert name.getDebugName(2) == "Regular"
    assert name.getDebugName(16) == "Test Merged"
    assert name.getDebugName(17) == "Light"
    assert name.getDebugName(4) == "Test Merged Light"
    assert name.getDebugName(6) == "TestMerged-Light"
    assert name.getDebugName(5) == "Version 1.000"
    assert "Test Latin" in name.getDebugName(10) and "Test CJK" in name.getDebugName(10)


def test_old_and_localized_names_removed(merged: dict[str, Any]) -> None:
    merged["font"]["name"].setName("芫荽", 1, 3, 1, 0x404)  # a zh-TW family name
    merged["font"]["name"].setName("Old Maker", 8, 3, 1, 0x409)
    name = build(merged)["name"]
    assert not [n for n in name.names if n.nameID == 1 and n.langID == 0x404]
    assert name.getDebugName(8) is None
    assert all(n.toUnicode() != "芫荽" for n in name.names)


def test_licence_text_combined(merged: dict[str, Any]) -> None:
    same = "SIL Open Font License 1.1"
    merged["w"] = with_license(merged["w"], license=same, copyright="Copyright A")
    merged["c"] = with_license(merged["c"], license=same, copyright="Copyright B")
    name = build(merged)["name"]
    assert name.getDebugName(13) == same  # identical texts collapse to one
    assert name.getDebugName(0) == "Test Latin: Copyright A\nTest CJK: Copyright B"


def test_line_metrics_written(merged: dict[str, Any]) -> None:
    font = build(merged)
    os2, hhea = font["OS/2"], font["hhea"]
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (880, -120, 0)
    assert (hhea.ascent, hhea.descent, hhea.lineGap) == (880, -120, 0)
    assert os2.fsSelection & USE_TYPO
    hi, lo = glyph_extents(font)
    assert os2.usWinAscent >= hi and os2.usWinDescent >= -lo


def test_line_metrics_max_mode(merged: dict[str, Any]) -> None:
    font = build(merged, metrics=MetricsConfig(line_height="max"))
    assert font["OS/2"].sTypoAscender == round(1900 * 1000 / 2048)


@pytest.mark.parametrize(
    ("style", "regular", "bold", "italic", "weight"),
    [
        ("Light", True, False, False, 300),
        ("Regular", True, False, False, 400),
        ("Bold", False, True, False, 700),
        ("Italic", False, False, True, 400),
        ("Bold Italic", False, True, True, 700),
    ],
)
def test_style_bits(
    merged: dict[str, Any], style: str, regular: bool, bold: bool, italic: bool, weight: int
) -> None:
    font = build(merged, style=style)
    sel = font["OS/2"].fsSelection
    assert bool(sel & REGULAR) is regular
    assert bool(sel & (1 << 5)) is bold
    assert bool(sel & 1) is italic
    assert font["OS/2"].usWeightClass == weight
    assert font["head"].macStyle == (1 if bold else 0) | (2 if italic else 0)


def test_strictest_fs_type_written(merged: dict[str, Any]) -> None:
    merged["c"] = dataclasses.replace(merged["c"], fs_type=8)
    assert build(merged)["OS/2"].fsType == 8


def test_os2_recalculated(merged: dict[str, Any], tmp_path: Path) -> None:
    font = build(merged)
    os2 = font["OS/2"]
    assert os2.achVendID == "NONE"
    assert os2.usFirstCharIndex == 0x20
    assert os2.sxHeight == round(1082 * 1000 / 2048)  # measured from the merged 'x'
    assert 59 in os2.getUnicodeRanges()  # CJK Unified Ideographs bit
    font.save(str(tmp_path / "m.ttf"))
    assert TTFont(str(tmp_path / "m.ttf"))["name"].getDebugName(6) == "TestMerged-Light"


def test_reserved_name_blocks_build(merged: dict[str, Any]) -> None:
    merged["w"] = with_license(merged["w"], reserved_font_names=("Merged",))
    with pytest.raises(ConfigError):
        build(merged)


def test_no_licence_still_builds(merged: dict[str, Any]) -> None:
    empty = LicenseInfo(None, None, None)
    merged["w"] = dataclasses.replace(merged["w"], license=empty)
    merged["c"] = dataclasses.replace(merged["c"], license=empty)
    assert build(merged)["name"].getDebugName(13) is None


# Real fonts -----------------------------------------------------------------------------


@pytest.mark.realfont
def test_real_names(real_merge: dict[str, Any]) -> None:
    name = real_merge["font"]["name"]
    assert name.getDebugName(1) == "Iansui Literata Light"
    assert name.getDebugName(16) == "Iansui Literata"
    assert name.getDebugName(17) == "Light"
    assert name.getDebugName(6) == "IansuiLiterata-Light"
    assert "Literata Project Authors" in name.getDebugName(0)
    assert "Iansui Project Authors" in name.getDebugName(0)
    assert "Open Font License" in name.getDebugName(13)
    assert {n.nameID for n in name.names} >= {0, 1, 2, 3, 4, 5, 6, 10, 13, 14, 16, 17}


@pytest.mark.realfont
def test_real_line_metrics_follow_iansui(real_merge: dict[str, Any]) -> None:
    os2, hhea = real_merge["font"]["OS/2"], real_merge["font"]["hhea"]
    assert (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap) == (940, -180, 0)
    assert (hhea.ascent, hhea.descent, hhea.lineGap) == (940, -180, 0)
    # Windows clipping covers the tallest glyph (a Vietnamese stacked capital).
    hi, lo = glyph_extents(real_merge["font"])
    assert os2.usWinAscent >= hi >= 1070
    assert os2.usWinDescent >= -lo


@pytest.mark.realfont
def test_real_pinyin_capitals_fit_line(real_merge: dict[str, Any]) -> None:
    font = real_merge["font"]
    cmap, glyf = font.getBestCmap(), font["glyf"]
    for ch in "ĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙ":
        assert glyf[cmap[ord(ch)]].yMax <= 940, ch


@pytest.mark.realfont
def test_real_style_and_os2(real_merge: dict[str, Any]) -> None:
    os2 = real_merge["font"]["OS/2"]
    assert os2.usWeightClass == 300
    assert os2.fsSelection & REGULAR and os2.fsSelection & USE_TYPO
    assert os2.fsType == 0
    assert (os2.sxHeight, os2.sCapHeight) == pytest.approx((485, 673), abs=3)


@pytest.mark.realfont
def test_real_font_saves_and_reloads(real_merge: dict[str, Any], tmp_path: Path) -> None:
    out = tmp_path / "IansuiLiterata-Light.ttf"
    real_merge["font"].save(str(out))
    font = TTFont(str(out))
    assert font["name"].getDebugName(4) == "Iansui Literata Light"
    assert len(font.getBestCmap()) == 13301
