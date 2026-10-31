"""Subsetter: cut each source font down to the codepoints the plan gives it.

Keeps every glyph the kept characters can reach through OpenType features (ligatures,
small caps, vertical forms), all name-table entries (so licence text survives), the
BASE table and vertical metrics. Works on a fresh copy of the font, so the
``FontSource`` stays untouched and can be inspected again.
"""

from __future__ import annotations

from collections.abc import Iterable

from fontTools import subset as ft_subset
from fontTools.ttLib import TTFont

from fontmerge.errors import RoutingError
from fontmerge.models import AssignmentPlan, FontSource, SubsetOptions

# fontTools drops these by default; fontmerge needs them.
_ALWAYS_KEEP = ("BASE", "vhea", "vmtx")


def reopen(src: FontSource) -> TTFont:
    """A fresh, independent ``TTFont`` for the same face."""
    return TTFont(str(src.path), fontNumber=src.face_index if src.is_collection else -1)


def subset_font(
    src: FontSource, codepoints: Iterable[int], opts: SubsetOptions | None = None
) -> TTFont:
    """Return a new font containing only ``codepoints`` (plus feature-reachable glyphs)."""
    opts = opts or SubsetOptions()
    wanted = set(codepoints)
    font = reopen(src)
    cmap = font.getBestCmap() or {}

    absent = wanted - set(cmap)
    if absent:
        sample = ", ".join(f"U+{cp:04X}" for cp in sorted(absent)[:5])
        raise RoutingError(
            f"{src.path.name} was asked for {len(absent)} characters it does not have: {sample}",
            hint="the plan must be built from this font's profile",
        )

    subsetter = ft_subset.Subsetter(options=_ft_options(opts))
    subsetter.populate(unicodes=wanted)
    subsetter.subset(font)
    return font


def subset_pair(
    western: FontSource,
    cjk: FontSource,
    plan: AssignmentPlan,
    opts: SubsetOptions | None = None,
) -> tuple[TTFont, TTFont]:
    """Subset both sources to their share of ``plan``."""
    return subset_font(western, plan.western, opts), subset_font(cjk, plan.cjk, opts)


def _ft_options(opts: SubsetOptions) -> ft_subset.Options:
    o = ft_subset.Options()
    o.layout_features = list(opts.layout_features)
    o.layout_scripts = ["*"]
    o.name_IDs = ["*"]
    o.name_languages = ["*"]
    o.name_legacy = True
    o.glyph_names = True
    o.notdef_glyph = True
    o.notdef_outline = True
    o.recommended_glyphs = False
    o.hinting = opts.keep_hinting
    o.legacy_kern = opts.keep_legacy_kern
    o.prune_unicode_ranges = True
    o.recalc_bounds = True
    drop = [t for t in o.drop_tables if t not in _ALWAYS_KEEP]
    o.drop_tables = drop + [t for t in opts.drop_tables if t not in drop]
    return o
