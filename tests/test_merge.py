"""Stage 5: Merger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fontTools.ttLib import TTFont

from fontfactory import build_latin_ttf
from fontmerge import merge as merge_mod
from fontmerge.errors import GlyphLimitError
from fontmerge.inspector import inspect_font
from fontmerge.loader import load_font
from fontmerge.merge import clash_renames, legacy_kern_to_gpos, merge_fonts, rename_glyphs
from fontmerge.models import MergeOptions, NormalizePlan, RoutingConfig, Source
from fontmerge.normalize import normalize
from fontmerge.router import build_plan
from fontmerge.subset import reopen, subset_pair


def features(font: TTFont, table: str) -> set[str]:
    return {r.FeatureTag for r in font[table].table.FeatureList.FeatureRecord}


def single_sub(font: TTFont, feature: str) -> dict[str, str]:
    """All single substitutions reachable from a GSUB feature."""
    gsub = font["GSUB"].table
    out: dict[str, str] = {}
    for rec in gsub.FeatureList.FeatureRecord:
        if rec.FeatureTag != feature:
            continue
        for i in rec.Feature.LookupListIndex:
            for st in gsub.LookupList.Lookup[i].SubTable:
                st = getattr(st, "ExtSubTable", st)
                out.update(getattr(st, "mapping", {}) or {})
    return out


def prepared(latin_ttf: Path, cjk_otf: Path, outline: str) -> tuple[TTFont, TTFont]:
    w_src, c_src = load_font(latin_ttf), load_font(cjk_otf)
    plan = build_plan(inspect_font(w_src), inspect_font(c_src), RoutingConfig())
    w, c = subset_pair(w_src, c_src, plan)
    norm = NormalizePlan(
        target_upm=1000, target_outline=outline, vertical_advance=1000, vertical_top=880
    )
    return normalize(w, c, norm)


# Merging generated fonts ----------------------------------------------------------------


@pytest.mark.parametrize("outline", ["glyf", "CFF"])
def test_merge(latin_ttf: Path, cjk_otf: Path, tmp_path: Path, outline: str) -> None:
    w, c = prepared(latin_ttf, cjk_otf, outline)
    w_cmap, c_cmap = dict(w.getBestCmap()), dict(c.getBestCmap())
    merged = merge_fonts(w, c)

    cmap = merged.getBestCmap()
    assert set(cmap) == set(w_cmap) | set(c_cmap)
    assert cmap[0x41] == "A"  # Latin from the Western font, with its own name
    assert cmap[0x4E00] == "uni4E00"
    assert merged.getGlyphOrder()[0] == ".notdef"
    assert merged["hmtx"]["A"][0] == w["hmtx"]["A"][0]
    assert "vert" in features(merged, "GSUB")
    assert single_sub(merged, "vert")["uni300C"] == "uni300C.vert"
    assert "kern" in features(merged, "GPOS")
    assert set(merged["vmtx"].metrics) == set(merged.getGlyphOrder())

    out = tmp_path / f"merged.{'ttf' if outline == 'glyf' else 'otf'}"
    merged.save(str(out))
    reloaded = TTFont(str(out))
    assert len(reloaded.getBestCmap()) == len(cmap)


def test_base_font_supplies_whole_font_tables(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = prepared(latin_ttf, cjk_otf, "glyf")
    assert merge_fonts(w, c)["name"].getDebugName(1) == "Test CJK"
    w, c = prepared(latin_ttf, cjk_otf, "glyf")
    western_first = merge_fonts(w, c, MergeOptions(base=Source.WESTERN))
    assert western_first["name"].getDebugName(1) == "Test Latin"


def test_glyph_limit(latin_ttf: Path, cjk_otf: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w, c = prepared(latin_ttf, cjk_otf, "glyf")
    monkeypatch.setattr(merge_mod, "MAX_GLYPHS", 10)
    with pytest.raises(GlyphLimitError) as exc:
        merge_fonts(w, c)
    assert exc.value.hint and "include_hangul" in exc.value.hint


# Glyph renaming -------------------------------------------------------------------------


def test_clash_renames_are_unique(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = reopen(load_font(latin_ttf)), reopen(load_font(cjk_otf))
    renames = clash_renames(w, c, ".cjk")
    assert renames["A"] == "A.cjk"
    assert ".notdef" not in renames
    assert "uni4E00" not in renames  # no clash


def test_clash_suffix_avoids_existing_names(latin_ttf: Path, cjk_otf: Path) -> None:
    w, c = reopen(load_font(latin_ttf)), reopen(load_font(cjk_otf))
    renames = clash_renames(w, c, ".vert")  # "ellipsis.vert" already exists in the CJK font
    assert renames["ellipsis"] == "ellipsis.vert2"


@pytest.mark.parametrize("fixture", ["latin_ttf", "cjk_otf"])
def test_rename_glyphs_updates_every_table(fixture: str, request: pytest.FixtureRequest) -> None:
    path: Path = request.getfixturevalue(fixture)
    font = reopen(load_font(path))
    renamed = rename_glyphs(font, {"A": "A.renamed"})
    assert "A.renamed" in renamed.getGlyphOrder() and "A" not in renamed.getGlyphOrder()
    assert renamed.getBestCmap()[0x41] == "A.renamed"
    assert renamed["hmtx"]["A.renamed"] == font["hmtx"]["A"]


def test_rename_updates_gsub_references(cjk_otf: Path, tmp_path: Path) -> None:
    font = reopen(load_font(cjk_otf))
    renamed = rename_glyphs(font, {"uni300C.vert": "bracket.v"})
    assert single_sub(renamed, "vert")["uni300C"] == "bracket.v"
    renamed.save(str(tmp_path / "r.otf"))
    assert "bracket.v" in TTFont(str(tmp_path / "r.otf")).getGlyphOrder()


# Legacy kern ----------------------------------------------------------------------------


def test_legacy_kern_dropped_when_gpos_exists(tmp_path: Path) -> None:
    path = build_latin_ttf(tmp_path / "k.ttf", legacy_kern={("A", "V"): -80})
    font = TTFont(str(path))
    legacy_kern_to_gpos(font)
    assert "kern" not in font and "GPOS" in font


def test_legacy_kern_converted_when_no_gpos(tmp_path: Path) -> None:
    path = build_latin_ttf(tmp_path / "k.ttf", legacy_kern={("A", "V"): -80, ("T", "o"): -40})
    font = TTFont(str(path))
    del font["GPOS"]
    legacy_kern_to_gpos(font)
    assert "kern" not in font
    assert features(font, "GPOS") == {"kern"}
    pairs = {}
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            if st.Format == 1:
                for first, ps in zip(st.Coverage.glyphs, st.PairSet, strict=True):
                    for rec in ps.PairValueRecord:
                        pairs[(first, rec.SecondGlyph)] = rec.Value1.XAdvance
    assert pairs == {("A", "V"): -80, ("T", "o"): -40}


# Real fonts -----------------------------------------------------------------------------


@pytest.mark.realfont
def test_real_merge_coverage(real_merge: dict[str, Any]) -> None:
    font, route = real_merge["font"], real_merge["route"]
    cmap = font.getBestCmap()
    assert set(cmap) == route.western | route.cjk
    assert len(cmap) == 13301
    assert cmap[0x41] == "A" and cmap[0x4E2D].startswith("uni4E2D")
    assert "A.cjk" in font.getGlyphOrder()  # Iansui's leftover Latin, renamed, unencoded


@pytest.mark.realfont
def test_real_merge_glyph_count(real_merge: dict[str, Any]) -> None:
    font, w, c = real_merge["font"], real_merge["western"], real_merge["cjk"]
    assert len(font.getGlyphOrder()) == len(w.getGlyphOrder()) + len(c.getGlyphOrder())


@pytest.mark.realfont
def test_real_merge_layout(real_merge: dict[str, Any]) -> None:
    font = real_merge["font"]
    gsub, gpos = features(font, "GSUB"), features(font, "GPOS")
    assert {"vert", "vkna", "hwid", "liga", "smcp", "onum", "ss01", "ss02"} <= gsub
    assert {"kern", "mark", "palt", "vpal", "halt", "vkrn"} <= gpos
    scripts = {r.ScriptTag for r in font["GSUB"].table.ScriptList.ScriptRecord}
    assert {"DFLT", "latn", "grek", "cyrl"} <= scripts


@pytest.mark.realfont
def test_real_merge_keeps_vertical_tables(real_merge: dict[str, Any]) -> None:
    font = real_merge["font"]
    for tag in ("BASE", "vhea", "vmtx"):
        assert tag in font
    assert set(font["vmtx"].metrics) == set(font.getGlyphOrder())
