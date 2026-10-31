"""Merger: combine the two normalized fonts into one.

Uses ``fontTools.merge.Merger``, which merges cmap, hmtx/vmtx, GDEF/GSUB/GPOS and the
other tables. Before merging, this module:

* checks the combined glyph count against the 65,535 limit;
* turns a legacy ``kern`` table into GPOS kerning when the font has no GPOS (apps
  ignore ``kern`` once GPOS exists), or drops it when GPOS is already there;
* renames CJK glyphs whose names clash with Western ones (``A`` -> ``A.cjk``), so the
  Western glyphs keep their standard names. Only the name-holding tables are rewritten;
  the rest are copied as compiled bytes, which keeps this fast on 20,000-glyph fonts.

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
    renames = clash_renames(western, cjk, opts.glyph_name_suffix)
    with tempfile.TemporaryDirectory(prefix="fontmerge-") as tmp:
        w_path, c_path = Path(tmp) / "western.ttf", Path(tmp) / "cjk.ttf"
        western.save(str(w_path))
        cjk.save(str(c_path))
        if renames:
            renamed = Path(tmp) / "cjk-renamed.ttf"
            renamed.write_bytes(_renamed_bytes(c_path.read_bytes(), renames))
            c_path = renamed
        paths = [c_path, w_path] if opts.base is Source.CJK else [w_path, c_path]
        try:
            merged = Merger(options=MergerOptions()).merge([str(p) for p in paths])
        except Exception as e:  # fontTools raises many types; report one
            raise MergeFailedError(f"fontTools could not merge the fonts: {e}") from e
        merged.ensureDecompiled()  # read everything while the temp files still exist

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
    """Return a copy of ``font`` with glyphs renamed everywhere they are referenced."""
    if not renames:
        return font
    buf = BytesIO()
    font.save(buf)
    return TTFont(BytesIO(_renamed_bytes(buf.getvalue(), renames)))


def _renamed_bytes(data: bytes, renames: dict[str, str]) -> bytes:
    """Rename glyphs in a compiled font, cheaply.

    Tables refer to glyphs by number, so only the tables that store names (post, or
    the CFF charset) change. The font is reopened lazily and its glyph order replaced
    before anything else is read; every other table is copied byte for byte on save.
    """
    font = TTFont(BytesIO(data), lazy=True)
    order = [renames.get(n, n) for n in font.getGlyphOrder()]
    if "CFF " in font:
        top = font["CFF "].cff.topDictIndex[0]
        cs = top.CharStrings
        cs.charStrings = {renames.get(k, k): v for k, v in cs.charStrings.items()}
        top.charset = order
    font.setGlyphOrder(order)
    if "post" in font:
        font["post"].glyphOrder = order
    out = BytesIO()
    font.save(out)
    return out.getvalue()


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
