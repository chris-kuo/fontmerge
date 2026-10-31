"""Inspector: read facts about a font without changing it.

``inspect_font`` produces a ``FontProfile`` that later stages plan from (UPM, coverage,
metrics, ideographic em box, features, licence). ``check_profile`` turns a profile into
``Issue``s for the font's role, e.g. a Western font with no Latin, or a licence that
forbids subsetting.
"""

from __future__ import annotations

import re
from typing import Any

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from fontmerge.models import (
    FontProfile,
    FontSource,
    Issue,
    LicenseInfo,
    Severity,
    Source,
    VerticalMetrics,
)

# OS/2 fsType bits (OpenType spec)
FS_RESTRICTED = 0x0002
FS_PREVIEW_PRINT = 0x0004
FS_EDITABLE = 0x0008
FS_NO_SUBSETTING = 0x0100
FS_BITMAP_ONLY = 0x0200

_USE_TYPO_METRICS = 1 << 7

_BASIC_LATIN_LETTERS = frozenset(range(0x41, 0x5B)) | frozenset(range(0x61, 0x7B))
_CJK_UNIFIED = range(0x4E00, 0xA000)
_KANA = range(0x3040, 0x3100)


def inspect_font(src: FontSource) -> FontProfile:
    font = src.ttfont
    upm = int(font["head"].unitsPerEm)
    cmap = font.getBestCmap() or {}
    ideo_embox, ideo_char_face = _base_ideographic(font, upm)

    return FontProfile(
        family_name=_family_name(font),
        upm=upm,
        glyph_count=int(font["maxp"].numGlyphs),
        codepoints=frozenset(cmap),
        outline=src.outline,
        metrics=_vertical_metrics(font),
        x_height=_os2_or_measured(font, cmap, "sxHeight", 0x78),
        cap_height=_os2_or_measured(font, cmap, "sCapHeight", 0x48),
        ideo_embox=ideo_embox,
        ideo_char_face=ideo_char_face,
        has_vertical_metrics="vhea" in font and "vmtx" in font,
        features=_layout_tags(font, "FeatureList"),
        scripts=_layout_tags(font, "ScriptList"),
        fs_type=int(font["OS/2"].fsType) if "OS/2" in font else 0,
        license=_license_info(font),
    )


def describe_fs_type(fs_type: int) -> str:
    """Plain-language summary of the OS/2 embedding permissions."""
    if fs_type & FS_RESTRICTED:
        level = "restricted license embedding"
    elif fs_type & FS_PREVIEW_PRINT:
        level = "preview and print embedding"
    elif fs_type & FS_EDITABLE:
        level = "editable embedding"
    else:
        level = "installable embedding"
    extras = []
    if fs_type & FS_NO_SUBSETTING:
        extras.append("no subsetting")
    if fs_type & FS_BITMAP_ONLY:
        extras.append("bitmap embedding only")
    return ", ".join([level, *extras])


def check_profile(profile: FontProfile, role: Source) -> list[Issue]:
    """Problems with using this font in the given role, most severe first."""
    issues: list[Issue] = []
    name = profile.family_name or "font"

    if profile.fs_type & FS_NO_SUBSETTING:
        issues.append(
            Issue(
                Severity.ERROR,
                "license-no-subsetting",
                f"{name}'s embedding permissions forbid subsetting, which merging requires",
            )
        )
    if profile.fs_type & FS_RESTRICTED:
        issues.append(
            Issue(
                Severity.WARNING,
                "license-restricted",
                f"{name} has restricted embedding permissions; check its licence allows "
                "modification before distributing the merged font",
            )
        )
    if profile.fs_type & FS_BITMAP_ONLY:
        issues.append(
            Issue(Severity.WARNING, "license-bitmap-only", f"{name} allows bitmap embedding only")
        )

    if role is Source.WESTERN:
        missing = _BASIC_LATIN_LETTERS - profile.codepoints
        if missing:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "role-coverage",
                    f"{name} is the Western font but lacks {len(missing)} of the 52 basic "
                    "Latin letters",
                    params={"font": name, "missing": len(missing)},
                )
            )
    else:
        han = sum(1 for cp in profile.codepoints if cp in _CJK_UNIFIED)
        kana = sum(1 for cp in profile.codepoints if cp in _KANA)
        if han < 100 and kana < 50:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "role-coverage",
                    f"{name} is the CJK font but has only {han} Han characters and {kana} kana",
                    params={"font": name, "han": han, "kana": kana},
                )
            )

    if profile.license.reserved_font_names:
        reserved = ", ".join(f'"{n}"' for n in profile.license.reserved_font_names)
        issues.append(
            Issue(
                Severity.INFO,
                "license-reserved-names",
                f"{name}'s licence reserves the names {reserved}; the merged font's name "
                "must not use them",
                params={"font": name, "names": list(profile.license.reserved_font_names)},
            )
        )
    if not (profile.license.license or profile.license.license_url):
        issues.append(
            Issue(
                Severity.INFO,
                "license-unknown",
                f"{name} has no licence information; make sure you may modify it",
                params={"font": name},
            )
        )

    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(issues, key=lambda i: order[i.severity])


# --------------------------------------------------------------------------------------


def _name(font: TTFont, name_id: int) -> str | None:
    if "name" not in font:
        return None
    value = font["name"].getDebugName(name_id)
    return value.strip() if value else None


def _family_name(font: TTFont) -> str:
    return _name(font, 16) or _name(font, 1) or ""


def _vertical_metrics(font: TTFont) -> VerticalMetrics:
    hhea = font["hhea"]
    os2 = font.get("OS/2")
    return VerticalMetrics(
        hhea_ascender=int(hhea.ascent),
        hhea_descender=int(hhea.descent),
        hhea_line_gap=int(hhea.lineGap),
        typo_ascender=int(os2.sTypoAscender) if os2 else int(hhea.ascent),
        typo_descender=int(os2.sTypoDescender) if os2 else int(hhea.descent),
        typo_line_gap=int(os2.sTypoLineGap) if os2 else int(hhea.lineGap),
        win_ascent=int(os2.usWinAscent) if os2 else int(hhea.ascent),
        win_descent=int(os2.usWinDescent) if os2 else -int(hhea.descent),
        use_typo_metrics=bool(os2 and os2.fsSelection & _USE_TYPO_METRICS),
    )


def _os2_or_measured(font: TTFont, cmap: dict[int, str], attr: str, codepoint: int) -> int | None:
    """OS/2 value when present and non-zero, else the yMax of the reference glyph."""
    os2 = font.get("OS/2")
    if os2 is not None and os2.version >= 2 and getattr(os2, attr, 0) > 0:
        return int(getattr(os2, attr))
    glyph_name = cmap.get(codepoint)
    if glyph_name is None:
        return None
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    if pen.bounds is None:
        return None
    y_max: float = pen.bounds[3]
    return round(y_max)


def _layout_tags(font: TTFont, list_name: str) -> frozenset[str]:
    tags: set[str] = set()
    for table_tag in ("GSUB", "GPOS"):
        if table_tag not in font:
            continue
        table = font[table_tag].table
        lst = getattr(table, list_name, None)
        if lst is None:
            continue
        if list_name == "FeatureList":
            tags.update(r.FeatureTag for r in lst.FeatureRecord)
        else:
            tags.update(r.ScriptTag for r in lst.ScriptRecord)
    return frozenset(tags)


def _base_ideographic(
    font: TTFont, upm: int
) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Ideographic em box and character face from the BASE table's horizontal axis.

    Uses the ``hani`` script's values, falling back to ``DFLT`` then the first script.
    The em box top is ``idtp`` when present, else ``ideo + upm``.
    """
    if "BASE" not in font:
        return None, None
    axis: Any = getattr(font["BASE"].table, "HorizAxis", None)
    if axis is None or axis.BaseTagList is None or axis.BaseScriptList is None:
        return None, None
    tags = list(axis.BaseTagList.BaselineTag)
    records = {r.BaseScriptTag: r for r in axis.BaseScriptList.BaseScriptRecord}
    record = records.get("hani") or records.get("DFLT") or next(iter(records.values()), None)
    if record is None or record.BaseScript.BaseValues is None:
        return None, None
    coords = [c.Coordinate for c in record.BaseScript.BaseValues.BaseCoord]
    values = dict(zip(tags, coords, strict=False))

    embox = None
    if "ideo" in values:
        bottom = int(values["ideo"])
        top = int(values.get("idtp", bottom + upm))
        embox = (bottom, top)
    char_face = None
    if "icfb" in values and "icft" in values:
        char_face = (int(values["icfb"]), int(values["icft"]))
    return embox, char_face


_RFN_SENTENCE = re.compile(r"Reserved\s+Font\s+Names?\b([^.\n]*)", re.IGNORECASE)
# Straight or curly quotes, double or single (written as escapes to keep the source ASCII).
_QUOTED = re.compile("[\"\u201c]([^\"\u201d]+)[\"\u201d]|['\u2018]([^'\u2019]+)['\u2019]")


def parse_reserved_font_names(*texts: str | None) -> tuple[str, ...]:
    """OFL Reserved Font Names declared in copyright or licence strings."""
    found: list[str] = []
    for text in texts:
        if not text:
            continue
        for sentence in _RFN_SENTENCE.findall(text):
            for double, single in _QUOTED.findall(sentence):
                name = (double or single).strip()
                if name and name not in found:
                    found.append(name)
    return tuple(found)


def _license_info(font: TTFont) -> LicenseInfo:
    copyright_ = _name(font, 0)
    license_ = _name(font, 13)
    return LicenseInfo(
        copyright=copyright_,
        license=license_,
        license_url=_name(font, 14),
        reserved_font_names=parse_reserved_font_names(copyright_, license_),
    )
