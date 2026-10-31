"""Stage 3: Subsetter."""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from fontfactory import build_latin_ttf
from fontmerge.errors import RoutingError
from fontmerge.inspector import inspect_font
from fontmerge.loader import load_font
from fontmerge.models import MAX_GLYPHS, AssignmentPlan, RoutingConfig, SubsetOptions
from fontmerge.router import build_plan
from fontmerge.subset import subset_font, subset_pair


def _features(font: TTFont, table: str) -> set[str]:
    if table not in font or font[table].table.FeatureList is None:
        return set()
    return {r.FeatureTag for r in font[table].table.FeatureList.FeatureRecord}


def _round_trip(font: TTFont, path: Path) -> TTFont:
    font.save(str(path))
    return TTFont(str(path))


# Generated fonts ----------------------------------------------------------------------


def test_cmap_is_exactly_the_requested_set(latin_ttf: Path) -> None:
    wanted = {ord(c) for c in "ABab "}
    out = subset_font(load_font(latin_ttf), wanted)
    assert set(out.getBestCmap()) == wanted
    assert out.getGlyphOrder()[0] == ".notdef"
    assert len(out.getGlyphOrder()) == len(wanted) + 1  # + .notdef


def test_bidi_mirror_not_added(iansui: Path) -> None:
    # Regression: merging Gentium Book Plus + Iansui failed with "wrong-source U+223C",
    # because asking Iansui for U+223D (reversed tilde) also kept its bidi mirror U+223C.
    font = subset_font(load_font(iansui), {0x223D, 0x28})
    assert set(font.getBestCmap()) == {0x223D, 0x28}


def test_kerning_kept_for_kept_glyphs(latin_ttf: Path) -> None:
    out = subset_font(load_font(latin_ttf), {0x41, 0x42})
    assert "kern" in _features(out, "GPOS")


def test_source_font_untouched(latin_ttf: Path) -> None:
    src = load_font(latin_ttf)
    before = len(src.ttfont.getBestCmap())
    subset_font(src, {0x41})
    assert len(src.ttfont.getBestCmap()) == before


def test_unknown_codepoint_rejected(latin_ttf: Path) -> None:
    with pytest.raises(RoutingError, match="U\\+4E00"):
        subset_font(load_font(latin_ttf), {0x41, 0x4E00})


def test_vertical_alternates_follow_their_base(cjk_otf: Path) -> None:
    out = subset_font(load_font(cjk_otf), {0x300C, 0x4E00})
    order = out.getGlyphOrder()
    assert "uni300C.vert" in order  # reachable through 'vert'
    assert "ellipsis.vert" not in order  # its base (ellipsis) was not kept
    assert "vert" in _features(out, "GSUB")


def test_cjk_tables_survive(cjk_otf: Path, tmp_path: Path) -> None:
    out = _round_trip(subset_font(load_font(cjk_otf), {0x4E00, 0x3042}), tmp_path / "c.otf")
    assert "CFF " in out
    for tag in ("BASE", "vhea", "vmtx"):
        assert tag in out, tag
    assert out["vhea"].numberOfVMetrics <= out["maxp"].numGlyphs


def test_legacy_kern_kept_by_default(tmp_path: Path) -> None:
    path = build_latin_ttf(tmp_path / "k.ttf", legacy_kern={("A", "V"): -80, ("A", "Z"): -10})
    src = load_font(path)
    kept = subset_font(src, {ord(c) for c in "AV"})
    assert "kern" in kept
    assert kept["kern"].kernTables[0].kernTable == {("A", "V"): -80}
    dropped = subset_font(src, {ord(c) for c in "AV"}, SubsetOptions(keep_legacy_kern=False))
    assert "kern" not in dropped


def test_names_and_licence_kept(tmp_path: Path) -> None:
    path = build_latin_ttf(
        tmp_path / "lic.ttf",
        extra_names={"licenseDescription": "OFL 1.1", "licenseInfoURL": "https://ofl.example"},
    )
    out = subset_font(load_font(path), {0x41})
    assert out["name"].getDebugName(13) == "OFL 1.1"
    assert out["name"].getDebugName(14) == "https://ofl.example"


def test_subset_pair_uses_the_plan(latin_ttf: Path, cjk_otf: Path) -> None:
    w_src, c_src = load_font(latin_ttf), load_font(cjk_otf)
    plan = build_plan(inspect_font(w_src), inspect_font(c_src), RoutingConfig())
    w, c = subset_pair(w_src, c_src, plan)
    assert set(w.getBestCmap()) == plan.western
    assert set(c.getBestCmap()) == plan.cjk
    assert 0x41 not in c.getBestCmap()  # the CJK font's own 'A' is gone


def test_empty_plan_keeps_notdef(latin_ttf: Path) -> None:
    out = subset_font(load_font(latin_ttf), set())
    assert out.getGlyphOrder() == [".notdef"]


# Real fonts ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_subsets(literata: Path, iansui: Path) -> tuple[TTFont, TTFont, AssignmentPlan]:
    w_src, c_src = load_font(literata), load_font(iansui)
    plan = build_plan(inspect_font(w_src), inspect_font(c_src), RoutingConfig())
    w, c = subset_pair(w_src, c_src, plan)
    return w, c, plan


@pytest.mark.realfont
def test_real_cmaps_match_plan(real_subsets: tuple[TTFont, TTFont, AssignmentPlan]) -> None:
    w, c, plan = real_subsets
    assert set(w.getBestCmap()) == plan.western
    assert set(c.getBestCmap()) == plan.cjk


@pytest.mark.realfont
def test_real_glyph_budget(real_subsets: tuple[TTFont, TTFont, AssignmentPlan]) -> None:
    w, c, _ = real_subsets
    # maxp.numGlyphs is only refreshed on save; the glyph order is current.
    total = len(w.getGlyphOrder()) + len(c.getGlyphOrder())
    assert total < MAX_GLYPHS
    assert len(c.getGlyphOrder()) < 15076  # Iansui lost its own Latin, Greek, Cyrillic


@pytest.mark.realfont
def test_real_feature_reachable_glyphs_kept(
    real_subsets: tuple[TTFont, TTFont, AssignmentPlan],
) -> None:
    w, _, plan = real_subsets
    # The arrow's codepoint goes to Iansui (symbols=cjk) ...
    assert plan.source_of(0x2190) is not None and 0x2190 not in w.getBestCmap()
    # ... but Literata's ss02 maps "a" to its arrow glyph, so the glyph stays, unencoded.
    assert "arrowleft" in w.getGlyphOrder()


@pytest.mark.realfont
def test_real_literata_keeps_features_drops_hinting_and_stat(
    real_subsets: tuple[TTFont, TTFont, AssignmentPlan],
) -> None:
    w, _, _ = real_subsets
    assert {"kern", "mark", "liga", "smcp", "onum", "ss01"} <= _features(w, "GSUB") | _features(
        w, "GPOS"
    )
    assert "prep" not in w and "STAT" not in w
    assert w["name"].getDebugName(13)  # licence text kept


@pytest.mark.realfont
def test_real_iansui_keeps_vertical_layout(
    real_subsets: tuple[TTFont, TTFont, AssignmentPlan],
) -> None:
    _, c, _ = real_subsets
    for tag in ("BASE", "vhea", "vmtx"):
        assert tag in c, tag
    assert {"vert", "vkna"} <= _features(c, "GSUB")
    assert {"palt", "vpal", "halt"} <= _features(c, "GPOS")


@pytest.mark.realfont
def test_real_subsets_round_trip(
    real_subsets: tuple[TTFont, TTFont, AssignmentPlan], tmp_path: Path
) -> None:
    w, c, plan = real_subsets
    w2 = _round_trip(w, tmp_path / "lit.ttf")
    c2 = _round_trip(c, tmp_path / "ian.ttf")
    assert len(w2.getBestCmap()) == len(plan.western)
    assert len(c2.getBestCmap()) == len(plan.cjk)
