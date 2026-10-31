"""Normalizer: make the two subset fonts compatible, and make the Latin sit well.

Steps, in order:

1. **Units per em**: rescale both fonts to ``plan.target_upm``.
2. **Outline format**: convert both to ``plan.target_outline`` (TrueType ``glyf`` or CFF).
3. **Western scale**: shrink or grow every Western value (outlines, advances, kerning,
   mark anchors, metrics) by ``plan.western_scale``, keeping units per em fixed.
4. **Western baseline shift**: move Western outlines up or down.
5. **Vertical metrics**: if the CJK font supports vertical writing, give every Western
   glyph a vertical advance and top side bearing that fit the CJK em box.

``plan_normalization`` turns the two profiles and the user config into a concrete
``NormalizePlan`` (e.g. working out the automatic scale).

Both fonts are modified in place and returned.
"""

from __future__ import annotations

import math
from typing import Any

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import ScalerVisitor, scale_upem

from fontmerge.models import FontProfile, NormalizeConfig, NormalizePlan

AUTO_SCALE_RANGE = (0.85, 1.15)
CU2QU_MAX_ERR = 1.0
"""Max distance (font units) between a cubic curve and its quadratic replacement."""


# --------------------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------------------


def auto_western_scale(western: FontProfile, cjk: FontProfile) -> float:
    """Scale that best matches the Western Latin to the CJK font's own Latin.

    The geometric mean of the x-height ratio and the cap-height ratio (each measured
    as a fraction of the em), so neither lowercase nor capitals drift far. Returns 1.0
    when either font lacks the metrics, and clamps to ``AUTO_SCALE_RANGE``.
    """
    if not (western.x_height and western.cap_height and cjk.x_height and cjk.cap_height):
        return 1.0
    xh = (cjk.x_height / cjk.upm) / (western.x_height / western.upm)
    cap = (cjk.cap_height / cjk.upm) / (western.cap_height / western.upm)
    scale = math.sqrt(xh * cap)
    lo, hi = AUTO_SCALE_RANGE
    return round(min(max(scale, lo), hi), 3)


def plan_normalization(
    western: FontProfile, cjk: FontProfile, cfg: NormalizeConfig | None = None
) -> NormalizePlan:
    cfg = cfg or NormalizeConfig()
    target_upm = cjk.upm
    if cfg.target_outline == "auto":
        target_outline = "CFF" if cjk.outline in ("CFF", "CFF2") else "glyf"
    else:
        target_outline = cfg.target_outline
    scale = cfg.western_scale if cfg.western_scale is not None else auto_western_scale(western, cjk)
    shift = cfg.western_baseline_shift if cfg.western_baseline_shift is not None else 0

    vertical_top = None
    if cjk.has_vertical_metrics:
        if cjk.ideo_embox is not None:
            vertical_top = cjk.ideo_embox[1]
        else:
            vertical_top = cjk.metrics.typo_ascender
    return NormalizePlan(
        target_upm=target_upm,
        target_outline=target_outline,  # type: ignore[arg-type]
        western_scale=scale,
        western_baseline_shift=shift,
        vertical_advance=target_upm if cjk.has_vertical_metrics else None,
        vertical_top=vertical_top,
    )


# --------------------------------------------------------------------------------------
# Normalizing
# --------------------------------------------------------------------------------------


def normalize(western: TTFont, cjk: TTFont, plan: NormalizePlan) -> tuple[TTFont, TTFont]:
    for font in (western, cjk):
        if font["head"].unitsPerEm != plan.target_upm:
            scale_upem(font, plan.target_upm)
        convert_outlines(font, plan.target_outline)

    if plan.western_scale != 1.0:
        scale_font(western, plan.western_scale)
    if plan.western_baseline_shift:
        shift_outlines(western, plan.western_baseline_shift)

    if plan.vertical_advance is not None and plan.vertical_top is not None:
        synthesize_vertical_metrics(western, cjk, plan.vertical_advance, plan.vertical_top)
    else:
        for tag in ("vhea", "vmtx", "VORG"):
            if tag in western:
                del western[tag]
    return western, cjk


def outline_format(font: TTFont) -> str:
    if "glyf" in font:
        return "glyf"
    if "CFF " in font:
        return "CFF"
    if "CFF2" in font:
        return "CFF2"
    raise ValueError("font has no outlines")


def scale_font(font: TTFont, factor: float) -> None:
    """Scale every design value by ``factor`` while keeping units per em unchanged."""
    upm = font["head"].unitsPerEm
    ScalerVisitor(factor).visit(font)
    font["head"].unitsPerEm = upm


def convert_outlines(font: TTFont, target: str) -> None:
    current = outline_format(font)
    if current == target:
        return
    if current == "CFF2":
        raise ValueError("CFF2 (variable) outlines are not supported")
    if target == "glyf":
        _cff_to_glyf(font)
    elif target == "CFF":
        _glyf_to_cff(font)
    else:
        raise ValueError(f"unknown outline format {target!r}")


def shift_outlines(font: TTFont, dy: int) -> None:
    """Move every outline vertically by ``dy`` font units (advances are unchanged)."""
    if "glyf" in font:
        glyf = font["glyf"]
        for name in font.getGlyphOrder():
            glyph = glyf[name]
            if glyph.numberOfContours > 0:
                glyph.coordinates.translate((0, dy))
        # Composite offsets stay: their components have moved already.
        for name in font.getGlyphOrder():
            glyf[name].recalcBounds(glyf)
    else:
        _redraw_cff(font, (1, 0, 0, 1, 0, dy))


def synthesize_vertical_metrics(western: TTFont, cjk: TTFont, advance: int, top: int) -> None:
    """Give every Western glyph vertical metrics matching the CJK font's em box.

    Upright Latin in vertical text then advances one em per glyph, with its top side
    bearing measured from the top of the ideographic em box.
    """
    glyph_set = western.getGlyphSet()
    metrics: dict[str, tuple[int, int]] = {}
    for name in western.getGlyphOrder():
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(pen)
        tsb = top - math.ceil(pen.bounds[3]) if pen.bounds else 0
        metrics[name] = (advance, tsb)

    vmtx = newTable("vmtx")
    vmtx.metrics = metrics
    western["vmtx"] = vmtx

    vhea = newTable("vhea")
    src = cjk.get("vhea")
    vhea.tableVersion = 0x00011000
    vhea.ascent = src.ascent if src else advance // 2
    vhea.descent = src.descent if src else -(advance // 2)
    vhea.lineGap = src.lineGap if src else 0
    vhea.caretSlopeRise = 0
    vhea.caretSlopeRun = 1
    vhea.caretOffset = 0
    vhea.reserved1 = vhea.reserved2 = vhea.reserved3 = vhea.reserved4 = 0
    vhea.metricDataFormat = 0
    vhea.numberOfVMetrics = len(metrics)
    vhea.advanceHeightMax = advance
    vhea.minTopSideBearing = min(t for _, t in metrics.values())
    vhea.minBottomSideBearing = 0
    vhea.yMaxExtent = 0
    western["vhea"] = vhea
    if "VORG" in western:
        del western["VORG"]


# --------------------------------------------------------------------------------------
# Outline conversion helpers
# --------------------------------------------------------------------------------------


def _cff_to_glyf(font: TTFont) -> None:
    glyph_set = font.getGlyphSet()
    glyphs: dict[str, Any] = {}
    for name in font.getGlyphOrder():
        tt_pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(tt_pen, CU2QU_MAX_ERR, reverse_direction=True))
        glyphs[name] = tt_pen.glyph()

    del font["CFF "]
    if "VORG" in font:
        del font["VORG"]
    glyf = newTable("glyf")
    glyf.glyphOrder = font.getGlyphOrder()
    glyf.glyphs = glyphs
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    font["head"].glyphDataFormat = 0
    font["head"].indexToLocFormat = 0

    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for attr in (
        "maxZones",
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
        "maxComponentElements",
    ):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    font.sfntVersion = "\x00\x01\x00\x00"
    for name, glyph in glyphs.items():
        glyph.recalcBounds(glyf)
        adv, _ = font["hmtx"][name]
        font["hmtx"][name] = (adv, glyph.xMin if glyph.numberOfContours else 0)


def _glyf_to_cff(font: TTFont) -> None:
    glyph_set = font.getGlyphSet()
    charstrings = {}
    for name in font.getGlyphOrder():
        pen = T2CharStringPen(font["hmtx"][name][0], glyph_set)
        glyph_set[name].draw(pen)
        charstrings[name] = pen.getCharString()

    ps_name = _ps_name(font)
    for tag in ("glyf", "loca", "fpgm", "prep", "cvt ", "gasp"):
        if tag in font:
            del font[tag]
    fb = FontBuilder(font=font)
    fb.isTTF = False
    fb.setupCFF(ps_name, {"FullName": ps_name}, charstrings, {})
    font["maxp"].tableVersion = 0x00005000
    font["post"].formatType = 3.0
    font.sfntVersion = "OTTO"


def _redraw_cff(font: TTFont, transform: tuple[float, ...]) -> None:
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    charstrings = top.CharStrings
    glyph_set = font.getGlyphSet()
    new = {}
    for name in font.getGlyphOrder():
        pen = T2CharStringPen(font["hmtx"][name][0], None)
        glyph_set[name].draw(TransformPen(pen, transform))
        new[name] = pen.getCharString(private=charstrings[name].private)
    for name, cs in new.items():
        charstrings[name] = cs


def _ps_name(font: TTFont) -> str:
    name = font["name"].getDebugName(6) if "name" in font else None
    return name or "Merged-Regular"
