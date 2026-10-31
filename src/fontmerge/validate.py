"""Validator: check the merged font before it is written.

Each check adds ``Issue``s with a severity:

* **error**: the font is broken or wrong, and is not written (glyph limit, planned
  characters missing or from the wrong font, incomplete vertical metrics, bad names,
  OTS rejection).
* **warning**: the font works but something may look wrong (blank glyphs, glyphs taller
  than the Windows clipping metrics). ``--strict`` turns these into blockers.
* **info**: worth knowing (glyphs that reach above the line height, OTS not installed).

``format_report`` renders a report as plain text for the command line.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from io import BytesIO

from fontTools.ttLib import TTFont

from fontmerge.models import (
    MAX_GLYPHS,
    AssignmentPlan,
    Issue,
    Severity,
    Source,
    ValidationReport,
)

_PS_NAME = re.compile(r"^[!-~]{1,63}$")  # printable ASCII, no spaces
_PS_FORBIDDEN = set("[](){}<>/%")
_REQUIRED_NAMES = (1, 2, 4, 6)
_SAMPLE = 8  # how many examples an issue message lists


def validate(
    font: TTFont,
    plan: AssignmentPlan,
    sources: tuple[TTFont, TTFont] | None = None,
    *,
    run_ots: bool = True,
) -> ValidationReport:
    """Check ``font`` against ``plan``.

    ``sources`` = (western, cjk) as passed to the Merger; when given, every planned
    character is checked to come from the right font (same advance and bounds).
    """
    issues: list[Issue] = []
    cmap = font.getBestCmap() or {}
    order = font.getGlyphOrder()

    _check_structure(font, order, issues)
    coverage = _check_coverage(font, cmap, plan, issues)
    if sources is not None:
        _check_sources(font, cmap, plan, sources, issues)
    _check_empty_glyphs(font, cmap, issues)
    _check_metrics(font, cmap, plan, issues)
    _check_vertical(font, order, issues)
    _check_names(font, issues)
    if run_ots:
        _check_ots(font, issues)

    order_key = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    issues.sort(key=lambda i: order_key[i.severity])
    return ValidationReport(issues=tuple(issues), glyph_count=len(order), coverage=coverage)


def format_report(report: ValidationReport) -> str:
    lines = [
        f"Glyphs: {report.glyph_count:,}",
        "Characters: "
        + ", ".join(f"{n:,} from the {s.value} font" for s, n in report.coverage.items()),
    ]
    counts = {s: len(report.by_severity(s)) for s in Severity}
    lines.append(
        f"Issues: {counts[Severity.ERROR]} errors, {counts[Severity.WARNING]} warnings, "
        f"{counts[Severity.INFO]} notes"
    )
    for issue in report.issues:
        lines.append(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------


def _fmt(cps: list[int]) -> str:
    shown = ", ".join(f"U+{cp:04X} {chr(cp)!r}" for cp in sorted(cps)[:_SAMPLE])
    return shown + (f" and {len(cps) - _SAMPLE} more" if len(cps) > _SAMPLE else "")


def _check_structure(font: TTFont, order: list[str], issues: list[Issue]) -> None:
    if len(order) > MAX_GLYPHS:
        issues.append(
            Issue(
                Severity.ERROR,
                "glyph-limit",
                f"{len(order):,} glyphs; OpenType allows at most {MAX_GLYPHS:,}",
            )
        )
    if not order or order[0] != ".notdef":
        issues.append(Issue(Severity.ERROR, "notdef", "the first glyph must be .notdef"))
    upm = font["head"].unitsPerEm
    if not 16 <= upm <= 16384:
        issues.append(Issue(Severity.ERROR, "upm", f"units per em {upm} is out of range"))


def _check_coverage(
    font: TTFont, cmap: dict[int, str], plan: AssignmentPlan, issues: list[Issue]
) -> dict[Source, int]:
    coverage: dict[Source, int] = {}
    for source, cps in ((Source.WESTERN, plan.western), (Source.CJK, plan.cjk)):
        missing = [cp for cp in cps if cp not in cmap]
        coverage[source] = len(cps) - len(missing)
        if missing:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "unmapped",
                    f"{len(missing)} characters planned from the {source.value} font are "
                    f"missing: {_fmt(missing)}",
                    codepoint=min(missing),
                )
            )
    extra = set(cmap) - plan.western - plan.cjk
    if extra:
        issues.append(
            Issue(
                Severity.WARNING,
                "unplanned",
                f"{len(extra)} characters are in the font but not in the plan: {_fmt(list(extra))}",
            )
        )
    return coverage


def _signature(font: TTFont) -> Callable[[str], tuple[int, ...]]:
    """Advance width plus outline bounds of a glyph, for comparing across fonts."""
    hmtx = font["hmtx"]
    if "glyf" in font:
        glyf = font["glyf"]

        def sig(name: str) -> tuple[int, ...]:
            g = glyf[name]
            if not g.numberOfContours:
                return (hmtx[name][0],)
            if not hasattr(g, "xMin"):
                g.recalcBounds(glyf)
            return (hmtx[name][0], g.xMin, g.yMin, g.xMax, g.yMax)

        return sig

    from fontTools.pens.boundsPen import BoundsPen

    gs = font.getGlyphSet()

    def sig_cff(name: str) -> tuple[int, ...]:
        pen = BoundsPen(gs)
        gs[name].draw(pen)
        b = tuple(round(v) for v in pen.bounds) if pen.bounds else ()
        return (hmtx[name][0], *b)

    return sig_cff


def _check_sources(
    font: TTFont,
    cmap: dict[int, str],
    plan: AssignmentPlan,
    sources: tuple[TTFont, TTFont],
    issues: list[Issue],
) -> None:
    merged_sig = _signature(font)
    for source, src_font, cps in (
        (Source.WESTERN, sources[0], plan.western),
        (Source.CJK, sources[1], plan.cjk),
    ):
        src_cmap = src_font.getBestCmap() or {}
        src_sig = _signature(src_font)
        wrong = [
            cp
            for cp in cps
            if cp in cmap and cp in src_cmap and merged_sig(cmap[cp]) != src_sig(src_cmap[cp])
        ]
        if wrong:
            issues.append(
                Issue(
                    Severity.ERROR,
                    "wrong-source",
                    f"{len(wrong)} characters do not match their glyph in the "
                    f"{source.value} font: {_fmt(wrong)}",
                    codepoint=min(wrong),
                )
            )


def _expected_blank(cp: int) -> bool:
    """Spaces, controls and format characters are meant to have no outline."""
    return unicodedata.category(chr(cp)) in {"Zs", "Zl", "Zp", "Cc", "Cf", "Mn"} or cp in {
        0x115F,
        0x1160,
        0x3164,
        0xFFA0,
    }


def _check_empty_glyphs(font: TTFont, cmap: dict[int, str], issues: list[Issue]) -> None:
    if "glyf" in font:
        glyf = font["glyf"]

        def empty(name: str) -> bool:
            contours: int = glyf[name].numberOfContours
            return contours == 0

    else:
        from fontTools.pens.boundsPen import BoundsPen

        gs = font.getGlyphSet()

        def empty(name: str) -> bool:
            pen = BoundsPen(gs)
            gs[name].draw(pen)
            return pen.bounds is None

    blank = [cp for cp, name in cmap.items() if not _expected_blank(cp) and empty(name)]
    if blank:
        issues.append(
            Issue(
                Severity.WARNING,
                "empty-glyph",
                f"{len(blank)} visible characters have blank glyphs: {_fmt(blank)}",
                codepoint=min(blank),
            )
        )


def _y_extents(font: TTFont, names: list[str]) -> dict[str, tuple[int, int]]:
    if "glyf" in font:
        glyf = font["glyf"]
        out = {}
        for n in names:
            g = glyf[n]
            if g.numberOfContours:
                if not hasattr(g, "yMax"):
                    g.recalcBounds(glyf)
                out[n] = (g.yMin, g.yMax)
        return out
    from fontTools.pens.boundsPen import BoundsPen

    gs = font.getGlyphSet()
    out = {}
    for n in names:
        pen = BoundsPen(gs)
        gs[n].draw(pen)
        if pen.bounds:
            out[n] = (round(pen.bounds[1]), round(pen.bounds[3]))
    return out


def _check_metrics(
    font: TTFont, cmap: dict[int, str], plan: AssignmentPlan, issues: list[Issue]
) -> None:
    os2, hhea = font["OS/2"], font["hhea"]
    if os2.sTypoAscender <= 0 or os2.sTypoDescender > 0:
        issues.append(
            Issue(
                Severity.ERROR,
                "line-metrics",
                f"typo ascender/descender {os2.sTypoAscender}/{os2.sTypoDescender} look wrong",
            )
        )
    if (hhea.ascent, hhea.descent, hhea.lineGap) != (
        os2.sTypoAscender,
        os2.sTypoDescender,
        os2.sTypoLineGap,
    ):
        issues.append(
            Issue(
                Severity.INFO,
                "line-metrics-differ",
                "hhea and OS/2 typo line metrics differ; line spacing may vary between apps",
            )
        )

    extents = _y_extents(font, font.getGlyphOrder())
    if extents:
        hi = max(y for _, y in extents.values())
        lo = min(y for y, _ in extents.values())
        if hi > os2.usWinAscent or -lo > os2.usWinDescent:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "clipping",
                    f"glyphs reach {hi}/{lo} but the Windows clipping metrics are "
                    f"{os2.usWinAscent}/{-os2.usWinDescent}; Windows will cut them off",
                )
            )

    tall = [
        cp
        for cp in plan.western
        if cp in cmap and cmap[cp] in extents and extents[cmap[cp]][1] > os2.sTypoAscender
    ]
    if tall:
        issues.append(
            Issue(
                Severity.INFO,
                "tall-glyphs",
                f"{len(tall)} Western characters reach above the ascender "
                f"({os2.sTypoAscender}) and may touch the line above: {_fmt(tall)}",
            )
        )


def _check_vertical(font: TTFont, order: list[str], issues: list[Issue]) -> None:
    if "vhea" not in font and "vmtx" not in font:
        return
    if "vhea" not in font or "vmtx" not in font:
        issues.append(
            Issue(Severity.ERROR, "vertical", "vhea and vmtx must both be present or both absent")
        )
        return
    missing = [g for g in order if g not in font["vmtx"].metrics]
    if missing:
        issues.append(
            Issue(
                Severity.ERROR,
                "vertical",
                f"{len(missing)} glyphs have no vertical metrics, e.g. {', '.join(missing[:5])}",
                glyph=missing[0],
            )
        )


def _check_names(font: TTFont, issues: list[Issue]) -> None:
    name = font["name"]
    for nid in _REQUIRED_NAMES:
        if not name.getDebugName(nid):
            issues.append(Issue(Severity.ERROR, "names", f"name ID {nid} is missing"))
    ps = name.getDebugName(6)
    if ps and (not _PS_NAME.match(ps) or _PS_FORBIDDEN & set(ps)):
        issues.append(
            Issue(
                Severity.ERROR,
                "names",
                f"PostScript name {ps!r} must be at most 63 printable ASCII characters "
                "without spaces or []{}()<>/%",
            )
        )


def _check_ots(font: TTFont, issues: list[Issue]) -> None:
    try:
        import ots
    except ImportError:
        issues.append(
            Issue(
                Severity.INFO,
                "ots-skipped",
                "OTS sanitizer not installed, so the browser-compatibility check was skipped "
                "(pip install opentype-sanitizer)",
            )
        )
        return
    import tempfile
    from pathlib import Path

    buf = BytesIO()
    font.save(buf)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.ttf"
        path.write_bytes(buf.getvalue())
        result = ots.sanitize(str(path), str(Path(tmp) / "out.ttf"), capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or b"").decode(errors="replace").strip().splitlines()
        issues.append(
            Issue(
                Severity.ERROR,
                "ots",
                "OTS rejected the font (browsers would refuse it): "
                + ("; ".join(detail[:3]) or "no detail"),
            )
        )
