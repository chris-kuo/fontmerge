"""Metadata Builder: rewrite the font-wide tables of the merged font.

* **name**: the new family and style names, unique ID, version, PostScript name;
  copyright, designer and licence from both sources; a description saying how it was
  made. Old localized family names (e.g. Chinese names of the CJK font) are removed.
* **OS/2 and hhea**: line metrics chosen by ``MetricsConfig`` (CJK, Western or the
  larger of both), with Windows clipping metrics that cover every glyph; weight and
  style bits from the style name; the stricter embedding permission of the two sources;
  recalculated Unicode/code-page ranges, average width, x-height and cap height.
* **head**: version and style bits.

OFL Reserved Font Names of either source may not appear in the new names.
"""

from __future__ import annotations

import math
import re

from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from fontmerge.errors import ConfigError
from fontmerge.inspector import FS_EDITABLE, FS_PREVIEW_PRINT, FS_RESTRICTED
from fontmerge.models import (
    FontProfile,
    MetricsConfig,
    NamingConfig,
    NormalizePlan,
    VerticalMetrics,
)

WEIGHTS = {
    "thin": 100,
    "hairline": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "regular": 400,
    "book": 400,
    "normal": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}
RIBBI = {"regular", "italic", "bold", "bold italic"}

# Name IDs rewritten from scratch (all platforms and languages are removed first).
_REPLACED_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21, 22, 25)

_USE_TYPO_METRICS = 1 << 7
_FS_SEL_ITALIC = 1 << 0
_FS_SEL_BOLD = 1 << 5
_FS_SEL_REGULAR = 1 << 6


def build_metadata(
    font: TTFont,
    western: FontProfile,
    cjk: FontProfile,
    naming: NamingConfig,
    metrics: MetricsConfig | None = None,
    plan: NormalizePlan | None = None,
) -> TTFont:
    metrics = metrics or MetricsConfig()
    check_reserved_names(naming, western, cjk)
    _write_names(font, western, cjk, naming)
    _write_style(font, naming)
    _write_line_metrics(font, western, cjk, metrics, plan)
    _write_os2_misc(font, western, cjk, naming)
    return font


# --------------------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------------------


def check_reserved_names(naming: NamingConfig, *profiles: FontProfile) -> None:
    family = naming.family.casefold()
    squashed = family.replace(" ", "")
    for p in profiles:
        for reserved in p.license.reserved_font_names:
            r = reserved.casefold()
            if r in family or r.replace(" ", "") in squashed:
                raise ConfigError(
                    f'the family name "{naming.family}" uses "{reserved}", a Reserved Font '
                    f"Name of {p.family_name}; the OFL forbids it for modified fonts",
                    hint="choose a family name without it",
                )


def postscript_name(naming: NamingConfig) -> str:
    def clean(s: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", s)

    return f"{clean(naming.family)}-{clean(naming.style)}"[:63]


def style_names(naming: NamingConfig) -> dict[int, str]:
    """Name IDs 1, 2, 16, 17 following the RIBBI convention."""
    style = naming.style
    if style.casefold() in RIBBI:
        return {1: naming.family, 2: style}
    return {1: f"{naming.family} {style}", 2: "Regular", 16: naming.family, 17: style}


def _join_unique(*parts: str | None, sep: str = "\n") -> str | None:
    seen: list[str] = []
    for p in parts:
        if p and p.strip() and p.strip() not in seen:
            seen.append(p.strip())
    return sep.join(seen) if seen else None


def _labelled(western: FontProfile, cjk: FontProfile, w: str | None, c: str | None) -> str | None:
    if w and c and w.strip() == c.strip():
        return w.strip()
    return _join_unique(
        f"{western.family_name}: {w}" if w else None,
        f"{cjk.family_name}: {c}" if c else None,
    )


def _write_names(
    font: TTFont, western: FontProfile, cjk: FontProfile, naming: NamingConfig
) -> None:
    name = font["name"]
    name.names = [n for n in name.names if n.nameID not in _REPLACED_IDS]

    ps = postscript_name(naming)
    entries: dict[int, str | None] = {
        **style_names(naming),
        0: _labelled(western, cjk, western.license.copyright, cjk.license.copyright),
        3: f"{naming.version};{naming.vendor_id.strip() or 'NONE'};{ps}",
        4: f"{naming.family} {naming.style}"
        if naming.style.casefold() != "regular"
        else naming.family,
        5: f"Version {naming.version}",
        6: ps,
        10: (
            f"Merged by fontmerge: Western scripts from {western.family_name}, "
            f"Chinese and Japanese from {cjk.family_name}."
        ),
        13: _labelled(western, cjk, western.license.license, cjk.license.license),
        14: _join_unique(western.license.license_url, cjk.license.license_url, sep=" "),
    }
    for name_id, value in sorted(entries.items()):
        if value:
            name.setName(value, name_id, 3, 1, 0x409)
            if name_id in (1, 2, 4, 6, 16, 17) and value.isascii():
                name.setName(value, name_id, 1, 0, 0)


# --------------------------------------------------------------------------------------
# Style, weight, embedding
# --------------------------------------------------------------------------------------


def weight_class(style: str) -> int | None:
    key = style.casefold().replace(" ", "").replace("-", "").replace("italic", "")
    return WEIGHTS.get(key or "regular")


def strictest_fs_type(*fs_types: int) -> int:
    """Most restrictive embedding level of the inputs, plus any extra flag bits."""
    levels = [t & 0x000F for t in fs_types]
    if any(lv & FS_RESTRICTED for lv in levels):
        level = FS_RESTRICTED
    elif any(lv & FS_PREVIEW_PRINT for lv in levels):
        level = FS_PREVIEW_PRINT
    elif any(lv & FS_EDITABLE for lv in levels):
        level = FS_EDITABLE
    else:
        level = 0
    extras = 0
    for t in fs_types:
        extras |= t & 0x0300
    return level | extras


def _write_style(font: TTFont, naming: NamingConfig) -> None:
    style = naming.style.casefold()
    italic = "italic" in style or "oblique" in style
    bold = weight_class(naming.style) == 700
    os2 = font["OS/2"]
    sel = os2.fsSelection & ~(_FS_SEL_ITALIC | _FS_SEL_BOLD | _FS_SEL_REGULAR)
    if italic:
        sel |= _FS_SEL_ITALIC
    if bold:
        sel |= _FS_SEL_BOLD
    if not italic and not bold:
        # "Regular" in the RIBBI sense: any upright, non-bold style (Light included).
        sel |= _FS_SEL_REGULAR
    os2.fsSelection = sel
    wc = weight_class(naming.style)
    if wc is not None:
        os2.usWeightClass = wc
    font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    font["head"].fontRevision = float(naming.version)


# --------------------------------------------------------------------------------------
# Line metrics
# --------------------------------------------------------------------------------------


def _used(m: VerticalMetrics) -> tuple[int, int, int]:
    if m.use_typo_metrics:
        return m.typo_ascender, m.typo_descender, m.typo_line_gap
    return m.hhea_ascender, m.hhea_descender, m.hhea_line_gap


def line_metrics(
    western: FontProfile,
    cjk: FontProfile,
    mode: str,
    target_upm: int,
    western_scale: float = 1.0,
) -> tuple[int, int, int]:
    """(ascender, descender, line gap) in target units for the chosen mode."""
    cf = target_upm / cjk.upm
    wf = target_upm / western.upm * western_scale
    c = tuple(round(v * cf) for v in _used(cjk.metrics))
    w = tuple(round(v * wf) for v in _used(western.metrics))
    if mode == "cjk":
        return c  # type: ignore[return-value]
    if mode == "western":
        return w  # type: ignore[return-value]
    return max(c[0], w[0]), min(c[1], w[1]), max(c[2], w[2])


def glyph_extents(font: TTFont) -> tuple[int, int]:
    """(highest yMax, lowest yMin) over all glyphs."""
    if "glyf" in font:
        glyf = font["glyf"]
        hi, lo = 0, 0
        for name in font.getGlyphOrder():
            g = glyf[name]
            if g.numberOfContours:
                if not hasattr(g, "yMax"):
                    g.recalcBounds(glyf)
                hi, lo = max(hi, g.yMax), min(lo, g.yMin)
        return hi, lo
    gs = font.getGlyphSet()
    hi_f, lo_f = 0.0, 0.0
    for name in font.getGlyphOrder():
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        if pen.bounds:
            hi_f, lo_f = max(hi_f, pen.bounds[3]), min(lo_f, pen.bounds[1])
    return math.ceil(hi_f), math.floor(lo_f)


def _write_line_metrics(
    font: TTFont,
    western: FontProfile,
    cjk: FontProfile,
    metrics: MetricsConfig,
    plan: NormalizePlan | None,
) -> None:
    upm = font["head"].unitsPerEm
    scale = plan.western_scale if plan else 1.0
    asc, desc, gap = line_metrics(western, cjk, metrics.line_height, upm, scale)
    hi, lo = glyph_extents(font)

    os2, hhea = font["OS/2"], font["hhea"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = asc, desc, gap
    hhea.ascent, hhea.descent, hhea.lineGap = asc, desc, gap
    os2.fsSelection |= _USE_TYPO_METRICS
    if os2.version < 4:
        os2.version = 4
    # Windows clips glyphs outside the win metrics, so they must cover every glyph.
    os2.usWinAscent = max(asc, hi, cjk.metrics.win_ascent * upm // cjk.upm)
    os2.usWinDescent = max(-desc, -lo, cjk.metrics.win_descent * upm // cjk.upm)


# --------------------------------------------------------------------------------------
# Other OS/2 fields
# --------------------------------------------------------------------------------------


def _measure(font: TTFont, codepoint: int) -> int | None:
    name = (font.getBestCmap() or {}).get(codepoint)
    if name is None:
        return None
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return round(pen.bounds[3]) if pen.bounds else None


def _write_os2_misc(
    font: TTFont, western: FontProfile, cjk: FontProfile, naming: NamingConfig
) -> None:
    os2 = font["OS/2"]
    os2.achVendID = (naming.vendor_id + "    ")[:4]
    os2.fsType = strictest_fs_type(western.fs_type, cjk.fs_type)
    os2.recalcUnicodeRanges(font)
    os2.recalcCodePageRanges(font)
    os2.updateFirstAndLastCharIndex(font)
    os2.recalcAvgCharWidth(font)
    x_height = _measure(font, 0x78)
    cap_height = _measure(font, 0x48)
    if x_height:
        os2.sxHeight = x_height
    if cap_height:
        os2.sCapHeight = cap_height
    os2.usMaxContext = maxCtxFont(font)
