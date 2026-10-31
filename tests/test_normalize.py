"""Stage 4: Normalizer."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from fontfactory import CJK_UPM, LATIN_CAP_HEIGHT, LATIN_UPM, LATIN_X_HEIGHT
from fontmerge.inspector import inspect_font
from fontmerge.loader import load_font
from fontmerge.models import NormalizeConfig, NormalizePlan, RoutingConfig
from fontmerge.normalize import (
    auto_western_scale,
    convert_outlines,
    normalize,
    outline_format,
    plan_normalization,
    scale_font,
    shift_outlines,
)
from fontmerge.router import build_plan
from fontmerge.subset import reopen, subset_pair


def bounds(font: TTFont, glyph: str) -> tuple[float, float, float, float]:
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[glyph].draw(pen)
    assert pen.bounds is not None
    return pen.bounds  # type: ignore[no-any-return]


def kern_value(font: TTFont, left: str, right: str) -> int | None:
    """First pair-adjustment XAdvance for (left, right) in GPOS, format 1 subtables."""
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            st = getattr(st, "ExtSubTable", st)
            if getattr(st, "LookupType", None) != 2 or st.Format != 1:
                continue
            cov = st.Coverage.glyphs
            if left not in cov:
                continue
            for rec in st.PairSet[cov.index(left)].PairValueRecord:
                if rec.SecondGlyph == right:
                    return int(rec.Value1.XAdvance)
    return None


def round_trip(font: TTFont, path: Path) -> TTFont:
    font.save(str(path))
    return TTFont(str(path))


@pytest.fixture
def latin(latin_ttf: Path) -> TTFont:
    return reopen(load_font(latin_ttf))


@pytest.fixture
def cjk(cjk_otf: Path) -> TTFont:
    return reopen(load_font(cjk_otf))


# Planning -------------------------------------------------------------------------------


def test_plan_defaults(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = inspect_font(load_font(latin_ttf)), inspect_font(load_font(cjk_otf))
    plan = plan_normalization(w, c)
    assert plan.target_upm == CJK_UPM
    assert plan.target_outline == "CFF"  # follows the CJK font
    assert plan.western_scale == auto_western_scale(w, c)
    assert plan.western_baseline_shift == 0
    assert plan.vertical_advance == CJK_UPM
    assert plan.vertical_top == 880  # top of the BASE ideographic em box


def test_plan_respects_config(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = inspect_font(load_font(latin_ttf)), inspect_font(load_font(cjk_otf))
    plan = plan_normalization(
        w, c, NormalizeConfig(target_outline="glyf", western_scale=0.96, western_baseline_shift=-10)
    )
    assert (plan.target_outline, plan.western_scale, plan.western_baseline_shift) == (
        "glyf",
        0.96,
        -10,
    )


def test_plan_without_cjk_vertical_metrics(latin_ttf: Path) -> None:
    p = inspect_font(load_font(latin_ttf))
    plan = plan_normalization(p, p)  # "CJK" font with no vmtx
    assert plan.vertical_advance is None and plan.vertical_top is None


def test_auto_scale_formula(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = inspect_font(load_font(latin_ttf)), inspect_font(load_font(cjk_otf))
    xh = (540 / 1000) / (LATIN_X_HEIGHT / LATIN_UPM)
    cap = (730 / 1000) / (LATIN_CAP_HEIGHT / LATIN_UPM)
    assert auto_western_scale(w, c) == round((xh * cap) ** 0.5, 3)


# Individual operations ------------------------------------------------------------------


def test_scale_font_keeps_upm_and_scales_everything(latin: TTFont) -> None:
    before_adv = latin["hmtx"]["H"][0]
    before_kern = kern_value(latin, "A", "B")
    scale_font(latin, 0.5)
    assert latin["head"].unitsPerEm == LATIN_UPM
    assert latin["hmtx"]["H"][0] == round(before_adv * 0.5)
    assert bounds(latin, "H")[3] == pytest.approx(LATIN_CAP_HEIGHT * 0.5, abs=1)
    assert before_kern is not None
    assert kern_value(latin, "A", "B") == round(before_kern * 0.5)
    assert latin["OS/2"].sxHeight == round(LATIN_X_HEIGHT * 0.5)


@pytest.mark.parametrize("dy", [50, -30])
def test_shift_glyf(latin: TTFont, dy: int) -> None:
    before = bounds(latin, "H")
    adv = latin["hmtx"]["H"][0]
    shift_outlines(latin, dy)
    after = bounds(latin, "H")
    assert after[1] == before[1] + dy and after[3] == before[3] + dy
    assert latin["hmtx"]["H"][0] == adv
    assert latin["glyf"]["H"].yMin == before[1] + dy  # stored bounds updated


def test_shift_cff(cjk: TTFont, tmp_path: Path) -> None:
    before = bounds(cjk, "uni4E00")
    shift_outlines(cjk, 40)
    reloaded = round_trip(cjk, tmp_path / "s.otf")
    assert bounds(reloaded, "uni4E00")[1] == before[1] + 40


def test_cff_to_glyf(cjk: TTFont, tmp_path: Path) -> None:
    before = {g: bounds(cjk, g) for g in ("uni4E00", "uni3042", "A")}
    convert_outlines(cjk, "glyf")
    assert outline_format(cjk) == "glyf"
    reloaded = round_trip(cjk, tmp_path / "c.ttf")
    assert "glyf" in reloaded and "CFF " not in reloaded
    assert reloaded["maxp"].tableVersion == 0x00010000
    for g, b in before.items():
        assert bounds(reloaded, g) == pytest.approx(b, abs=1)
    assert reloaded.getBestCmap()[0x4E00] == "uni4E00"


def test_glyf_to_cff(latin: TTFont, tmp_path: Path) -> None:
    before = {g: bounds(latin, g) for g in ("H", "x", "g")}
    convert_outlines(latin, "CFF")
    reloaded = round_trip(latin, tmp_path / "l.otf")
    assert "CFF " in reloaded and "glyf" not in reloaded
    assert reloaded.sfntVersion == "OTTO"
    for g, b in before.items():
        assert bounds(reloaded, g) == pytest.approx(b, abs=1)


def test_convert_same_format_is_noop(latin: TTFont) -> None:
    glyf = latin["glyf"]
    convert_outlines(latin, "glyf")
    assert latin["glyf"] is glyf


# Full normalize -------------------------------------------------------------------------


def test_normalize_to_cff(latin: TTFont, cjk: TTFont, tmp_path: Path) -> None:
    plan = NormalizePlan(
        target_upm=1000,
        target_outline="CFF",
        western_scale=0.9,
        vertical_advance=1000,
        vertical_top=880,
    )
    w, c = normalize(latin, cjk, plan)
    factor = 1000 / LATIN_UPM * 0.9
    assert w["head"].unitsPerEm == c["head"].unitsPerEm == 1000
    assert outline_format(w) == outline_format(c) == "CFF"
    w = round_trip(w, tmp_path / "w.otf")
    assert bounds(w, "H")[3] == pytest.approx(LATIN_CAP_HEIGHT * factor, abs=1.5)
    assert bounds(w, "x")[3] == pytest.approx(LATIN_X_HEIGHT * factor, abs=1.5)


def test_normalize_to_glyf(latin: TTFont, cjk: TTFont, tmp_path: Path) -> None:
    plan = NormalizePlan(target_upm=1000, target_outline="glyf")
    w, c = normalize(latin, cjk, plan)
    assert outline_format(w) == outline_format(c) == "glyf"
    round_trip(c, tmp_path / "c.ttf")


def test_vertical_metrics_synthesized(latin: TTFont, cjk: TTFont, tmp_path: Path) -> None:
    plan = NormalizePlan(
        target_upm=1000, target_outline="CFF", vertical_advance=1000, vertical_top=880
    )
    w, _ = normalize(latin, cjk, plan)
    vmtx = w["vmtx"]
    assert set(vmtx.metrics) == set(w.getGlyphOrder())
    adv, tsb = vmtx["H"]
    assert adv == 1000
    assert tsb == 880 - round(bounds(w, "H")[3])
    assert vmtx["space"] == (w["hmtx"]["space"][0], 0)  # blank: its own width, not an em
    assert w["vhea"].ascent == cjk["vhea"].ascent
    reloaded = round_trip(w, tmp_path / "v.otf")
    assert reloaded["vmtx"]["H"] == (1000, tsb)
    assert reloaded["vmtx"]["space"] == vmtx["space"]


def test_no_vertical_metrics_when_cjk_has_none(latin: TTFont, cjk: TTFont) -> None:
    latin_with_vmtx = copy.deepcopy(latin)
    plan_v = NormalizePlan(
        target_upm=1000, target_outline="glyf", vertical_advance=1000, vertical_top=880
    )
    normalize(latin_with_vmtx, copy.deepcopy(cjk), plan_v)
    assert "vmtx" in latin_with_vmtx
    plan = NormalizePlan(target_upm=1000, target_outline="glyf")
    w, _ = normalize(latin_with_vmtx, cjk, plan)
    assert "vmtx" not in w and "vhea" not in w


# Real fonts -----------------------------------------------------------------------------


def first_mark_base_anchor(font: TTFont) -> tuple[str, int, int] | None:
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            st: Any = getattr(st, "ExtSubTable", st)
            if getattr(st, "LookupType", None) == 4:
                glyph = st.BaseCoverage.glyphs[0]
                anchor = st.BaseArray.BaseRecord[0].BaseAnchor[0]
                return glyph, int(anchor.XCoordinate), int(anchor.YCoordinate)
    return None


@pytest.fixture(scope="module")
def real_normalized(literata: Path, iansui: Path) -> dict[str, Any]:
    w_src, c_src = load_font(literata), load_font(iansui)
    w_prof, c_prof = inspect_font(w_src), inspect_font(c_src)
    route = build_plan(w_prof, c_prof, RoutingConfig())
    w, c = subset_pair(w_src, c_src, route)
    before = {
        "H": bounds(w, "H"),
        "x": bounds(w, "x"),
        "n_adv": w["hmtx"]["n"][0],
        "anchor": first_mark_base_anchor(w),
        "cjk_glyphs": len(c.getGlyphOrder()),
    }
    plan = plan_normalization(w_prof, c_prof, NormalizeConfig(western_scale=0.96))
    w, c = normalize(w, c, plan)
    return {
        "w": w,
        "c": c,
        "plan": plan,
        "before": before,
        "auto": auto_western_scale(w_prof, c_prof),
    }


@pytest.mark.realfont
def test_real_auto_scale_is_about_96_percent(real_normalized: dict[str, Any]) -> None:
    assert real_normalized["auto"] == pytest.approx(0.96, abs=0.005)


@pytest.mark.realfont
def test_real_plan(real_normalized: dict[str, Any]) -> None:
    plan = real_normalized["plan"]
    assert (plan.target_upm, plan.target_outline, plan.western_scale) == (1000, "glyf", 0.96)
    assert (plan.vertical_advance, plan.vertical_top) == (1000, 880)


@pytest.mark.realfont
def test_real_literata_scaled_to_96_percent(real_normalized: dict[str, Any]) -> None:
    w, before = real_normalized["w"], real_normalized["before"]
    assert bounds(w, "H")[3] == pytest.approx(before["H"][3] * 0.96, abs=1)  # cap 701 -> 673
    assert bounds(w, "x")[3] == pytest.approx(before["x"][3] * 0.96, abs=1)  # x 505 -> 485
    assert w["hmtx"]["n"][0] == round(before["n_adv"] * 0.96)
    assert w["head"].unitsPerEm == 1000


@pytest.mark.realfont
def test_real_mark_anchors_scaled(real_normalized: dict[str, Any]) -> None:
    w, before = real_normalized["w"], real_normalized["before"]
    glyph, x0, y0 = before["anchor"]
    g, x1, y1 = first_mark_base_anchor(w)
    assert g == glyph
    assert (x1, y1) == (round(x0 * 0.96), round(y0 * 0.96))


@pytest.mark.realfont
def test_real_literata_vertical_metrics(real_normalized: dict[str, Any]) -> None:
    w = real_normalized["w"]
    assert set(w["vmtx"].metrics) == set(w.getGlyphOrder())
    adv, tsb = w["vmtx"]["H"]
    assert adv == 1000
    assert tsb == 880 - round(bounds(w, "H")[3])


@pytest.mark.realfont
def test_real_iansui_unchanged_in_size(real_normalized: dict[str, Any]) -> None:
    c, before = real_normalized["c"], real_normalized["before"]
    assert c["head"].unitsPerEm == 1000
    assert len(c.getGlyphOrder()) == before["cjk_glyphs"]
    assert bounds(c, c.getBestCmap()[0x4E2D])[3] < 880  # 中 sits inside the em box


@pytest.mark.realfont
def test_real_normalized_fonts_save(real_normalized: dict[str, Any], tmp_path: Path) -> None:
    w = round_trip(real_normalized["w"], tmp_path / "w.ttf")
    assert "vmtx" in w and w["head"].unitsPerEm == 1000
