"""Stage 0: the generated test fonts are valid and have the properties tests rely on."""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from fontfactory import CJK_UPM, LATIN_UPM, LATIN_X_HEIGHT


def _features(font: TTFont, table: str) -> set[str]:
    return {r.FeatureTag for r in font[table].table.FeatureList.FeatureRecord}


def test_latin_font(latin_ttf: Path) -> None:
    font = TTFont(str(latin_ttf))
    assert font["head"].unitsPerEm == LATIN_UPM
    assert "glyf" in font and "CFF " not in font
    cmap = font.getBestCmap()
    assert cmap[0x41] == "A" and cmap[0x2026] == "ellipsis"
    assert font["OS/2"].sxHeight == LATIN_X_HEIGHT
    assert "kern" in _features(font, "GPOS")
    assert "vmtx" not in font


def test_cjk_font(cjk_otf: Path) -> None:
    font = TTFont(str(cjk_otf))
    assert font["head"].unitsPerEm == CJK_UPM
    assert "CFF " in font and "glyf" not in font
    cmap = font.getBestCmap()
    for cp in (0x4E00, 0x3042, 0x30A2, 0x3001, 0xFF21, 0xAC00, 0x41):
        assert cp in cmap, f"U+{cp:04X} missing"
    assert "vhea" in font and "vmtx" in font
    assert "vert" in _features(font, "GSUB")
    assert "BASE" in font


def test_cjk_font_round_trips(cjk_otf: Path, tmp_path: Path) -> None:
    out = tmp_path / "copy.otf"
    TTFont(str(cjk_otf)).save(str(out))
    assert TTFont(str(out)).getBestCmap()[0x4E16] == "uni4E16"


def test_collection_has_two_named_faces(cjk_ttc: Path) -> None:
    coll = TTCollection(str(cjk_ttc))
    names = [f["name"].getDebugName(1) for f in coll.fonts]
    assert names == ["Test CJK SC", "Test CJK JP"]


def test_variable_font_has_fvar(variable_ttf: Path) -> None:
    assert "fvar" in TTFont(str(variable_ttf))
