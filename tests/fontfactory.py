"""Build tiny, deterministic test fonts in code.

These stand in for real fonts in unit tests: they load in milliseconds and every
value (UPM, metrics, coverage, features) is known exactly. Each glyph is a simple
rectangle so outlines exist and can be scaled, converted and compared.

* ``build_latin_ttf``: Western font, TrueType outlines, UPM 2048, kerning.
* ``build_cjk_otf``: CJK font, CFF outlines, UPM 1000, vertical metrics, ``vert``,
  BASE table, and a few Latin glyphs of its own (as real CJK fonts have).
* ``build_ttc``: a collection of several fonts.
* ``build_variable_ttf``: a font with an ``fvar`` table, to test rejection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont


@dataclass(frozen=True)
class GlyphSpec:
    name: str
    codepoint: int | None
    advance: int
    box: tuple[int, int, int, int] | None
    """(xMin, yMin, xMax, yMax) of a rectangle outline; ``None`` = empty glyph."""


def _draw_rect(pen: object, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    pen.moveTo((x0, y0))  # type: ignore[attr-defined]
    pen.lineTo((x0, y1))  # type: ignore[attr-defined]
    pen.lineTo((x1, y1))  # type: ignore[attr-defined]
    pen.lineTo((x1, y0))  # type: ignore[attr-defined]
    pen.closePath()  # type: ignore[attr-defined]


# Latin font: UPM 2048, glyf outlines -------------------------------------------------

LATIN_UPM = 2048
LATIN_X_HEIGHT = 1082
LATIN_CAP_HEIGHT = 1456
LATIN_ASCENDER = 1900
LATIN_DESCENDER = -500

_UPPER = tuple(
    GlyphSpec(chr(cp), cp, 1300, (40, 0, 1260, LATIN_CAP_HEIGHT)) for cp in range(0x41, 0x5B)
)
# Lowercase: x-height boxes, except a few with ascenders or descenders.
_ASCENDERS = set("bdfhklt")
_DESCENDERS = set("gjpqy")
_LOWER = tuple(
    GlyphSpec(
        chr(cp),
        cp,
        1100,
        (
            60,
            -450 if chr(cp) in _DESCENDERS else 0,
            1040,
            1556 if chr(cp) in _ASCENDERS else LATIN_X_HEIGHT,
        ),
    )
    for cp in range(0x61, 0x7B)
)

LATIN_GLYPHS: tuple[GlyphSpec, ...] = (
    GlyphSpec(".notdef", None, 1200, (100, 0, 1100, 1456)),
    GlyphSpec("space", 0x0020, 520, None),
    *_UPPER,
    *_LOWER,
    GlyphSpec("one", 0x0031, 1150, (200, 0, 900, LATIN_CAP_HEIGHT)),
    GlyphSpec("hyphen", 0x002D, 700, (100, 500, 600, 640)),
    GlyphSpec("quoteleft", 0x2018, 500, (120, 1100, 380, 1456)),
    GlyphSpec("quoteright", 0x2019, 500, (120, 1100, 380, 1456)),
    GlyphSpec("endash", 0x2013, 1100, (0, 500, 1100, 620)),
    GlyphSpec("ellipsis", 0x2026, 1800, (150, 0, 1650, 200)),
    GlyphSpec("Aacute", 0x00C1, 1340, (20, 0, 1320, 1900)),
)

LATIN_FEA = """
languagesystem DFLT dflt;
languagesystem latn dflt;
feature kern {
    pos A B -60;
    pos a b -20;
} kern;
"""


# CJK font: UPM 1000, CFF outlines, vertical metrics ---------------------------------

CJK_UPM = 1000
CJK_ASCENDER = 880
CJK_DESCENDER = -120
CJK_FULL = (50, -70, 950, 830)

CJK_GLYPHS: tuple[GlyphSpec, ...] = (
    GlyphSpec(".notdef", None, 1000, (100, -120, 900, 880)),
    GlyphSpec("space", 0x0020, 224, None),
    # Latin glyphs the CJK font also carries (proportional Latin, like Noto Sans CJK)
    GlyphSpec("A", 0x0041, 650, (10, 0, 640, 730)),
    GlyphSpec("a", 0x0061, 560, (50, -10, 510, 540)),
    GlyphSpec("hyphen", 0x002D, 350, (40, 230, 310, 300)),
    GlyphSpec("quoteleft", 0x2018, 1000, (600, 550, 900, 830)),
    GlyphSpec("quoteright", 0x2019, 1000, (100, 550, 400, 830)),
    GlyphSpec("endash", 0x2013, 1000, (0, 300, 1000, 360)),
    GlyphSpec("ellipsis", 0x2026, 1000, (100, 300, 900, 400)),
    # CJK punctuation
    GlyphSpec("uni3001", 0x3001, 1000, (80, -60, 300, 160)),
    GlyphSpec("uni3002", 0x3002, 1000, (80, -60, 320, 180)),
    GlyphSpec("uni300C", 0x300C, 1000, (500, 300, 900, 830)),
    GlyphSpec("uni300C.vert", None, 1000, (170, 400, 700, 800)),
    GlyphSpec("ellipsis.vert", None, 1000, (450, 100, 550, 900)),
    # Kana
    GlyphSpec("uni3042", 0x3042, 1000, CJK_FULL),
    GlyphSpec("uni30A2", 0x30A2, 1000, CJK_FULL),
    # Han
    GlyphSpec("uni4E00", 0x4E00, 1000, (50, 330, 950, 430)),
    GlyphSpec("uni4E16", 0x4E16, 1000, CJK_FULL),
    GlyphSpec("uni754C", 0x754C, 1000, CJK_FULL),
    # Full-width Latin and Hangul
    GlyphSpec("uniFF21", 0xFF21, 1000, (120, 0, 880, 730)),
    GlyphSpec("uniAC00", 0xAC00, 1000, CJK_FULL),
)

CJK_FEA = """
languagesystem DFLT dflt;
languagesystem hani dflt;
languagesystem kana dflt;
languagesystem latn dflt;
feature vert {
    sub uni300C by uni300C.vert;
    sub ellipsis by ellipsis.vert;
} vert;
table BASE {
    HorizAxis.BaseTagList ideo romn;
    HorizAxis.BaseScriptList DFLT ideo -120 0,
                             hani ideo -120 0,
                             kana ideo -120 0,
                             latn romn -120 0;
} BASE;
"""


def _new_builder(upm: int, glyphs: Sequence[GlyphSpec], is_ttf: bool) -> FontBuilder:
    fb = FontBuilder(upm, isTTF=is_ttf)
    fb.setupGlyphOrder([g.name for g in glyphs])
    fb.setupCharacterMap({g.codepoint: g.name for g in glyphs if g.codepoint is not None})
    return fb


def _hmtx(glyphs: Sequence[GlyphSpec]) -> dict[str, tuple[int, int]]:
    return {g.name: (g.advance, g.box[0] if g.box else 0) for g in glyphs}


def _names(family: str, style: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    ps = f"{family.replace(' ', '')}-{style}"
    return (extra or {}) | {
        "familyName": family,
        "styleName": style,
        "uniqueFontIdentifier": f"fontmerge-test:{ps}",
        "fullName": f"{family} {style}",
        "psName": ps,
        "version": "Version 1.000",
    }


def build_latin_ttf(
    path: Path,
    *,
    family: str = "Test Latin",
    fs_type: int = 0,
    glyphs: Sequence[GlyphSpec] = LATIN_GLYPHS,
    extra_names: dict[str, str] | None = None,
    os2_overrides: dict[str, int] | None = None,
) -> Path:
    """Write a TrueType-flavoured Western test font and return its path.

    ``extra_names`` adds name-table entries (fontBuilder keys such as ``"copyright"``
    or ``"licenseDescription"``); ``os2_overrides`` replaces OS/2 values.
    """
    fb = _new_builder(LATIN_UPM, glyphs, is_ttf=True)
    outlines = {}
    for g in glyphs:
        pen = TTGlyphPen(None)
        if g.box:
            _draw_rect(pen, g.box)
        outlines[g.name] = pen.glyph()
    fb.setupGlyf(outlines)
    fb.setupHorizontalMetrics(_hmtx(glyphs))
    fb.setupHorizontalHeader(ascent=LATIN_ASCENDER, descent=LATIN_DESCENDER)
    fb.setupNameTable(_names(family, "Regular", extra_names))
    os2 = {
        "sTypoAscender": LATIN_ASCENDER,
        "sTypoDescender": LATIN_DESCENDER,
        "sTypoLineGap": 0,
        "usWinAscent": LATIN_ASCENDER,
        "usWinDescent": -LATIN_DESCENDER,
        "sxHeight": LATIN_X_HEIGHT,
        "sCapHeight": LATIN_CAP_HEIGHT,
        "fsType": fs_type,
    }
    fb.setupOS2(**(os2 | (os2_overrides or {})), achVendID="TEST")
    fb.setupPost()
    fb.addOpenTypeFeatures(LATIN_FEA)
    fb.save(str(path))
    return path


def build_cjk_otf(
    path: Path,
    *,
    family: str = "Test CJK",
    fs_type: int = 0,
    glyphs: Sequence[GlyphSpec] = CJK_GLYPHS,
    fea: str = CJK_FEA,
) -> Path:
    """Write a CFF-flavoured CJK test font with vertical metrics and return its path."""
    fb = _new_builder(CJK_UPM, glyphs, is_ttf=False)
    charstrings = {}
    for g in glyphs:
        pen = T2CharStringPen(g.advance, None)
        if g.box:
            _draw_rect(pen, g.box)
        charstrings[g.name] = pen.getCharString()
    names = _names(family, "Regular")
    fb.setupCFF(names["psName"], {"FullName": names["fullName"]}, charstrings, {})
    fb.setupHorizontalMetrics(_hmtx(glyphs))
    fb.setupHorizontalHeader(ascent=CJK_ASCENDER, descent=CJK_DESCENDER)
    fb.setupVerticalHeader(ascent=500, descent=-500)
    fb.setupVerticalMetrics(
        {g.name: (CJK_UPM, (CJK_ASCENDER - g.box[3]) if g.box else 0) for g in glyphs}
    )
    fb.setupNameTable(names)
    fb.setupOS2(
        sTypoAscender=CJK_ASCENDER,
        sTypoDescender=CJK_DESCENDER,
        sTypoLineGap=0,
        usWinAscent=1100,
        usWinDescent=300,
        sxHeight=540,
        sCapHeight=730,
        fsType=fs_type,
        achVendID="TEST",
    )
    fb.setupPost()
    fb.addOpenTypeFeatures(fea)
    fb.save(str(path))
    return path


def build_ttc(path: Path, font_paths: Sequence[Path]) -> Path:
    """Bundle several font files into one TrueType/OpenType collection."""
    collection = TTCollection()
    collection.fonts = [TTFont(str(p)) for p in font_paths]
    collection.save(str(path))
    return path


def build_variable_ttf(path: Path) -> Path:
    """Write a minimal font with an ``fvar`` table (used to test rejection)."""
    glyphs = LATIN_GLYPHS[:3]
    fb = _new_builder(LATIN_UPM, glyphs, is_ttf=True)
    outlines = {}
    for g in glyphs:
        pen = TTGlyphPen(None)
        if g.box:
            _draw_rect(pen, g.box)
        outlines[g.name] = pen.glyph()
    fb.setupGlyf(outlines)
    fb.setupHorizontalMetrics(_hmtx(glyphs))
    fb.setupHorizontalHeader(ascent=LATIN_ASCENDER, descent=LATIN_DESCENDER)
    fb.setupNameTable(_names("Test Variable", "Regular"))
    fb.setupOS2()
    fb.setupPost()
    fb.setupFvar(axes=[("wght", 100, 400, 900, "Weight")], instances=[])
    fb.save(str(path))
    return path
