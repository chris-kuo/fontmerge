"""Stage 1: Inspector."""

from __future__ import annotations

from pathlib import Path

import pytest

from fontfactory import (
    CJK_ASCENDER,
    CJK_DESCENDER,
    CJK_UPM,
    LATIN_ASCENDER,
    LATIN_CAP_HEIGHT,
    LATIN_DESCENDER,
    LATIN_GLYPHS,
    LATIN_UPM,
    LATIN_X_HEIGHT,
    build_cjk_otf,
    build_latin_ttf,
)
from fontmerge.inspector import (
    FS_NO_SUBSETTING,
    FS_RESTRICTED,
    check_profile,
    describe_fs_type,
    inspect_font,
    parse_reserved_font_names,
)
from fontmerge.loader import load_font
from fontmerge.models import FontProfile, Severity, Source


def _profile(path: Path) -> FontProfile:
    return inspect_font(load_font(path))


def _codes(issues: list) -> list[str]:  # type: ignore[type-arg]
    return [i.code for i in issues]


# Generated fonts ----------------------------------------------------------------------


def test_latin_profile(latin_ttf: Path) -> None:
    p = _profile(latin_ttf)
    assert p.family_name == "Test Latin"
    assert p.upm == LATIN_UPM
    assert p.outline == "glyf"
    assert p.glyph_count == len(LATIN_GLYPHS)
    assert p.codepoints == {g.codepoint for g in LATIN_GLYPHS if g.codepoint is not None}
    assert p.x_height == LATIN_X_HEIGHT
    assert p.cap_height == LATIN_CAP_HEIGHT
    assert p.metrics.hhea_ascender == LATIN_ASCENDER
    assert p.metrics.typo_descender == LATIN_DESCENDER
    assert p.metrics.win_descent == -LATIN_DESCENDER
    assert p.ideo_embox is None and p.ideo_char_face is None
    assert not p.has_vertical_metrics
    assert "kern" in p.features
    assert {"DFLT", "latn"} <= p.scripts
    assert p.fs_type == 0


def test_cjk_profile(cjk_otf: Path) -> None:
    p = _profile(cjk_otf)
    assert p.upm == CJK_UPM
    assert p.outline == "CFF"
    assert {0x4E00, 0x3042, 0xFF21, 0x41} <= p.codepoints
    assert p.ideo_embox == (-120, 880)  # from BASE: ideo = -120, top = ideo + UPM
    assert p.has_vertical_metrics
    assert "vert" in p.features
    assert {"hani", "kana"} <= p.scripts
    assert p.metrics.line_height == CJK_ASCENDER - CJK_DESCENDER


def test_x_height_measured_when_os2_is_zero(tmp_path: Path) -> None:
    path = build_latin_ttf(tmp_path / "nox.ttf", os2_overrides={"sxHeight": 0, "sCapHeight": 0})
    p = _profile(path)
    assert p.x_height == LATIN_X_HEIGHT  # yMax of the 'x' glyph
    assert p.cap_height == LATIN_CAP_HEIGHT  # yMax of the 'H' glyph


def test_x_height_none_without_reference_glyph(tmp_path: Path) -> None:
    glyphs = tuple(g for g in LATIN_GLYPHS if g.name != "x")
    path = build_latin_ttf(tmp_path / "nox2.ttf", glyphs=glyphs, os2_overrides={"sxHeight": 0})
    assert _profile(path).x_height is None


def test_use_typo_metrics_flag(tmp_path: Path) -> None:
    path = build_latin_ttf(
        tmp_path / "typo.ttf",
        os2_overrides={"fsSelection": 0x40 | 0x80, "sTypoLineGap": 100},
    )
    m = _profile(path).metrics
    assert m.use_typo_metrics
    assert m.line_height == LATIN_ASCENDER - LATIN_DESCENDER + 100


def test_license_and_reserved_names(tmp_path: Path) -> None:
    path = build_latin_ttf(
        tmp_path / "ofl.ttf",
        extra_names={
            "copyright": 'Copyright 2026 Example, with Reserved Font Name "Exemplar".',
            "licenseDescription": "This Font Software is licensed under the SIL OFL 1.1.",
            "licenseInfoURL": "https://openfontlicense.org",
        },
    )
    lic = _profile(path).license
    assert lic.reserved_font_names == ("Exemplar",)
    assert lic.license_url == "https://openfontlicense.org"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('with Reserved Font Names "Gentium" and "SIL".', ("Gentium", "SIL")),
        ('Reserved Font Name "Source". Other "quoted" text.', ("Source",)),
        ("Reserved Font Names “Noto” and “Han”.", ("Noto", "Han")),
        ("with Reserved Font Name 'Averia' and 'Averia Libre'.", ("Averia", "Averia Libre")),
        ("No reserved names here.", ()),
        (None, ()),
    ],
)
def test_parse_reserved_font_names(text: str | None, expected: tuple[str, ...]) -> None:
    assert parse_reserved_font_names(text) == expected


def test_reserved_names_deduplicated_across_fields() -> None:
    a = 'Reserved Font Name "Foo".'
    assert parse_reserved_font_names(a, a) == ("Foo",)


@pytest.mark.parametrize(
    ("fs_type", "words"),
    [
        (0, "installable"),
        (0x0002, "restricted"),
        (0x0004, "preview and print"),
        (0x0008, "editable"),
        (0x0108, "no subsetting"),
        (0x0200, "bitmap"),
    ],
)
def test_describe_fs_type(fs_type: int, words: str) -> None:
    assert words in describe_fs_type(fs_type)


# check_profile ------------------------------------------------------------------------


def test_clean_latin_font_has_no_warnings(latin_ttf: Path) -> None:
    issues = check_profile(_profile(latin_ttf), Source.WESTERN)
    assert all(i.severity is Severity.INFO for i in issues), issues


def test_tiny_cjk_font_warns_low_coverage(cjk_otf: Path) -> None:
    # The generated CJK font has only 3 Han characters, so it is flagged.
    # Real CJK fonts pass: see test_real_fonts_fit_their_roles.
    issues = check_profile(_profile(cjk_otf), Source.CJK)
    warnings = [i.code for i in issues if i.severity is Severity.WARNING]
    assert warnings == ["role-coverage"]


def test_no_subsetting_is_an_error(tmp_path: Path) -> None:
    path = build_cjk_otf(tmp_path / "nosub.otf", fs_type=FS_NO_SUBSETTING)
    issues = check_profile(_profile(path), Source.CJK)
    assert issues[0].severity is Severity.ERROR
    assert issues[0].code == "license-no-subsetting"


def test_restricted_is_a_warning(tmp_path: Path) -> None:
    path = build_latin_ttf(tmp_path / "restricted.ttf", fs_type=FS_RESTRICTED)
    assert "license-restricted" in _codes(check_profile(_profile(path), Source.WESTERN))


def test_wrong_role_warns(latin_ttf: Path, cjk_otf: Path) -> None:
    as_cjk = check_profile(_profile(latin_ttf), Source.CJK)
    assert "role-coverage" in _codes(as_cjk)
    as_western = check_profile(_profile(cjk_otf), Source.WESTERN)
    assert "role-coverage" in _codes(as_western)  # CJK test font lacks most of A-Z


def test_unknown_license_is_info(latin_ttf: Path) -> None:
    issues = check_profile(_profile(latin_ttf), Source.WESTERN)
    assert any(i.code == "license-unknown" and i.severity is Severity.INFO for i in issues)


# Real fonts ---------------------------------------------------------------------------


@pytest.mark.realfont
def test_averia_profile(averia: Path) -> None:
    p = _profile(averia)
    assert p.family_name == "Averia Serif Libre"
    assert p.upm == 2048
    assert p.outline == "glyf"
    assert (p.x_height, p.cap_height) == (956, 1387)
    assert set(range(0x20, 0x7F)) <= p.codepoints  # all of printable ASCII
    assert set(range(0xA0, 0x100)) <= p.codepoints  # all of Latin-1
    assert not any(0x370 <= cp <= 0x4FF for cp in p.codepoints)  # no Greek or Cyrillic
    assert p.features == frozenset()  # kerning is in the legacy 'kern' table, not GPOS
    assert p.license.reserved_font_names == ("Averia", "Averia Libre")
    assert not p.has_vertical_metrics


@pytest.mark.realfont
def test_iansui_profile(iansui: Path) -> None:
    p = _profile(iansui)
    assert p.family_name == "Iansui"
    assert p.upm == 1000
    assert p.outline == "glyf"
    assert sum(1 for cp in p.codepoints if 0x4E00 <= cp <= 0x9FFF) > 9000
    assert sum(1 for cp in p.codepoints if 0x3040 <= cp <= 0x30FF) > 150  # kana
    assert p.ideo_embox == (-120, 880)
    assert p.ideo_char_face == (-67, 827)
    assert p.has_vertical_metrics
    assert {"vert", "palt", "halt"} <= p.features
    assert p.license.reserved_font_names == ()
    assert p.glyph_count == 15076


@pytest.mark.realfont
def test_real_fonts_fit_their_roles(averia: Path, iansui: Path) -> None:
    g = check_profile(_profile(averia), Source.WESTERN)
    i = check_profile(_profile(iansui), Source.CJK)
    assert not [x for x in g + i if x.severity is not Severity.INFO]
    assert _codes(g) == ["license-reserved-names"]
    assert i == []
