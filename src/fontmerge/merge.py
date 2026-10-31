"""Merger: combine the two normalized fonts into one.

Uses ``fontTools.merge.Merger``, which merges cmap, hmtx/vmtx, GDEF/GSUB/GPOS and the
other tables. Before merging, this module:

* checks the combined glyph count against the 65,535 limit;
* turns a legacy ``kern`` table into GPOS kerning when the font has no GPOS (apps
  ignore ``kern`` once GPOS exists), or drops it when GPOS is already there;
* renames CJK glyphs whose names clash with Western ones (``A`` -> ``A.cjk``), so the
  Western glyphs keep their standard names.

The base font (CJK by default) goes first, so its whole-font tables (head, OS/2, BASE,
vhea, gasp) are the starting point. The Metadata Builder rewrites the font-wide values
afterwards.
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.merge import Merger
from fontTools.merge import Options as MergerOptions
from fontTools.ttLib import TTFont

from fontmerge.errors import GlyphLimitError, MergeFailedError
from fontmerge.models import MAX_GLYPHS, MergeOptions, Source


def merge_fonts(western: TTFont, cjk: TTFont, opts: MergeOptions | None = None) -> TTFont:
    opts = opts or MergeOptions()
    total = len(western.getGlyphOrder()) + len(cjk.getGlyphOrder())
    if total > MAX_GLYPHS:
        raise GlyphLimitError(
            f"the merged font would have {total:,} glyphs; the limit is {MAX_GLYPHS:,}",
            hint="leave out Hangul (include_hangul = false) or route fewer ranges to the CJK font",
        )

    legacy_kern_to_gpos(western)
    legacy_kern_to_gpos(cjk)
    cjk = rename_glyphs(cjk, clash_renames(western, cjk, opts.glyph_name_suffix))

    fonts = [cjk, western] if opts.base is Source.CJK else [western, cjk]
    with tempfile.TemporaryDirectory(prefix="fontmerge-") as tmp:
        paths = []
        for i, font in enumerate(fonts):
            path = Path(tmp) / f"part{i}.ttf"
            font.save(str(path))
            paths.append(str(path))
        try:
            merged = Merger(options=MergerOptions()).merge(paths)
        except Exception as e:  # fontTools raises many types; report one
            raise MergeFailedError(f"fontTools could not merge the fonts: {e}") from e
        # Decompile everything while the temp files still exist.
        buf = BytesIO()
        merged.save(buf)
    buf.seek(0)
    merged = TTFont(buf)

    expected = set(western.getBestCmap() or {}) | set(cjk.getBestCmap() or {})
    got = set(merged.getBestCmap() or {})
    if got != expected:
        lost = expected - got
        raise MergeFailedError(
            f"the merged font lost {len(lost)} characters, e.g. "
            + ", ".join(f"U+{cp:04X}" for cp in sorted(lost)[:5])
        )
    return merged


def clash_renames(western: TTFont, cjk: TTFont, suffix: str) -> dict[str, str]:
    """New names for CJK glyphs that share a name with a Western glyph."""
    w_names = set(western.getGlyphOrder())
    c_names = set(cjk.getGlyphOrder())
    taken = w_names | c_names
    renames: dict[str, str] = {}
    for name in sorted((w_names & c_names) - {".notdef"}):
        new = f"{name}{suffix}"
        n = 2
        while new in taken:
            new = f"{name}{suffix}{n}"
            n += 1
        taken.add(new)
        renames[name] = new
    return renames


def rename_glyphs(font: TTFont, renames: dict[str, str]) -> TTFont:
    """Return a copy of ``font`` with glyphs renamed everywhere they are referenced.

    Works by reloading the font and changing its glyph order before any table that
    refers to glyphs is decompiled, so every table picks up the new names.
    """
    if not renames:
        return font
    buf = BytesIO()
    font.save(buf)
    buf.seek(0)
    out = TTFont(buf)
    order = [renames.get(n, n) for n in out.getGlyphOrder()]
    if "CFF " in out:
        top = out["CFF "].cff.topDictIndex[0]
        cs = top.CharStrings
        cs.charStrings = {renames.get(k, k): v for k, v in cs.charStrings.items()}
        top.charset = order
    out.setGlyphOrder(order)
    out.ensureDecompiled()  # decompile every table now, under the new names
    return out


def legacy_kern_to_gpos(font: TTFont) -> None:
    """Replace a legacy ``kern`` table with GPOS kerning, or drop it if GPOS exists."""
    if "kern" not in font:
        return
    if "GPOS" in font:
        del font["kern"]
        return
    pairs: dict[tuple[str, str], int] = {}
    for sub in font["kern"].kernTables:
        if getattr(sub, "format", 0) == 0 and getattr(sub, "coverage", 1) & 1:
            pairs.update(sub.kernTable)
    del font["kern"]
    if not pairs:
        return
    lines = [f"    pos \\{a} \\{b} {v};" for (a, b), v in sorted(pairs.items()) if v]
    fea = (
        "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
        "feature kern {\n" + "\n".join(lines) + "\n} kern;\n"
    )
    addOpenTypeFeaturesFromString(font, fea, tables=["GPOS"])
