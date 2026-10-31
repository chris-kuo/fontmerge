"""Shared data models: the contracts passed between fontmerge modules.

Two kinds of model live here:

* **Config models** (Pydantic): built from CLI arguments and the TOML file, validated
  once, then read-only. ``MergeConfig`` is the root.
* **Runtime models** (frozen dataclasses): produced by one pipeline stage and consumed
  by the next (``FontSource`` -> ``FontProfile`` -> ``AssignmentPlan`` -> ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

MAX_CODEPOINT = 0x10FFFF
MAX_GLYPHS = 65535

OutlineFormat = Literal["glyf", "CFF", "CFF2"]


class Source(StrEnum):
    """Which input font a glyph or codepoint comes from."""

    WESTERN = "western"
    CJK = "cjk"


# --------------------------------------------------------------------------------------
# Config models
# --------------------------------------------------------------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceSpec(_Frozen):
    """An input font file, plus which face to use when the file is a collection."""

    path: Path
    face: int | str | None = None

    @field_validator("face")
    @classmethod
    def _face_not_negative(cls, v: int | str | None) -> int | str | None:
        if isinstance(v, int) and v < 0:
            raise ValueError("face index must be 0 or greater")
        if isinstance(v, str) and not v.strip():
            raise ValueError("face name must not be empty")
        return v


class PunctuationPolicy(StrEnum):
    """Which font supplies characters both fonts cover, such as quotes and dashes.

    * ``SPLIT``: ASCII/general punctuation from the Western font, full-width forms from CJK.
    * ``WESTERN``: Western font wherever it has the character.
    * ``CJK``: CJK font wherever it has the character.
    """

    SPLIT = "split"
    WESTERN = "western"
    CJK = "cjk"


def parse_codepoint(value: object) -> object:
    """Accept ``0x2018``, ``8216`` or ``"U+2018"`` / ``"2018"`` (hex) for a codepoint."""
    if isinstance(value, str):
        text = value.strip().upper()
        text = text[2:] if text.startswith(("U+", "0X")) else text
        try:
            return int(text, 16)
        except ValueError:
            raise ValueError(f"{value!r} is not a codepoint (use e.g. U+2018)") from None
    return value


class RangeOverride(_Frozen):
    """Force an inclusive codepoint range to a source font."""

    start: int = Field(ge=0, le=MAX_CODEPOINT)
    end: int = Field(ge=0, le=MAX_CODEPOINT)
    source: Source

    @field_validator("start", "end", mode="before")
    @classmethod
    def _codepoint(cls, v: object) -> object:
        return parse_codepoint(v)

    @model_validator(mode="after")
    def _ordered(self) -> RangeOverride:
        if self.start > self.end:
            raise ValueError(f"range start U+{self.start:04X} is after end U+{self.end:04X}")
        return self


class RoutingConfig(_Frozen):
    include_hangul: bool = False
    punctuation: PunctuationPolicy = PunctuationPolicy.SPLIT
    symbols: Source = Source.CJK
    """Which font supplies box drawing, arrows, geometric shapes and similar symbols."""
    fallback: bool = True
    """When the preferred font lacks a character, take it from the other font."""
    overrides: tuple[RangeOverride, ...] = ()
    """Force ranges to a font. Later overrides win. A forced font that lacks a
    character is ignored for that character, and the normal rules apply."""


class NormalizeConfig(_Frozen):
    target_outline: Literal["auto", "glyf", "CFF"] = "auto"
    western_scale: float | None = Field(default=None, gt=0, le=4)
    """Extra scale for Western glyphs after UPM matching. ``None`` = compute automatically."""
    western_baseline_shift: int | None = None
    """Vertical shift for Western glyphs, in target font units. ``None`` = automatic."""


class NamingConfig(_Frozen):
    family: str = Field(min_length=1, max_length=63)
    style: str = Field(default="Regular", min_length=1, max_length=63)
    version: str = Field(default="1.000", pattern=r"^\d+\.\d{3}$")
    vendor_id: str = Field(default="NONE", min_length=1, max_length=4)


class MetricsConfig(_Frozen):
    line_height: Literal["cjk", "western", "max"] = "cjk"
    """Whose line spacing the merged font uses: the CJK font's, the Western font's (after
    scaling), or the larger extents of both. Windows clipping metrics always cover every
    glyph, whatever this is set to."""


OutputFormat = Literal["ttf", "otf", "woff2"]


class OutputConfig(_Frozen):
    path: Path
    formats: tuple[OutputFormat, ...] = ()
    """Extra formats to write. Empty = infer one format from ``path``'s suffix."""
    write_report: bool = True
    preview: Literal["html", "png"] | None = None
    """Also write a preview sheet next to the font."""
    strict: bool = False

    @field_validator("path")
    @classmethod
    def _known_suffix(cls, v: Path) -> Path:
        if v.suffix.lower() not in {".ttf", ".otf", ".woff2"}:
            raise ValueError("output path must end in .ttf, .otf or .woff2")
        return v

    def resolved_formats(self) -> tuple[OutputFormat, ...]:
        primary: OutputFormat = self.path.suffix.lower().lstrip(".")  # type: ignore[assignment]
        extra = tuple(f for f in self.formats if f != primary)
        return (primary, *extra)


class MergeConfig(_Frozen):
    """Root configuration for one merge run."""

    western: SourceSpec
    cjk: SourceSpec
    output: OutputConfig
    naming: NamingConfig
    routing: RoutingConfig = RoutingConfig()
    normalize: NormalizeConfig = NormalizeConfig()
    metrics: MetricsConfig = MetricsConfig()


# --------------------------------------------------------------------------------------
# Runtime models
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceInfo:
    """Names of one face in a font file; a collection has several."""

    index: int
    family: str
    subfamily: str
    full_name: str
    postscript_name: str
    typographic_family: str | None = None

    def matches(self, name: str) -> bool:
        """Case-insensitive match against any of this face's names."""
        wanted = name.strip().casefold()
        candidates = (
            self.family,
            self.full_name,
            self.postscript_name,
            self.typographic_family,
        )
        return any(c and c.casefold() == wanted for c in candidates)


@dataclass(frozen=True, eq=False)
class FontSource:
    """A loaded font face. Produced by the Loader."""

    path: Path
    face_index: int
    ttfont: TTFont
    outline: OutlineFormat
    is_variable: bool
    is_collection: bool = False
    face: FaceInfo | None = None


@dataclass(frozen=True)
class VerticalMetrics:
    """The three sets of line metrics a font carries (hhea, OS/2 typo, OS/2 win)."""

    hhea_ascender: int
    hhea_descender: int
    hhea_line_gap: int
    typo_ascender: int
    typo_descender: int
    typo_line_gap: int
    win_ascent: int
    win_descent: int
    """Positive distance below the baseline, as stored in OS/2."""
    use_typo_metrics: bool
    """OS/2 fsSelection bit 7: apps should use the typo values for line spacing."""

    @property
    def line_height(self) -> int:
        """Default line height apps will use (typo if flagged, else hhea)."""
        if self.use_typo_metrics:
            return self.typo_ascender - self.typo_descender + self.typo_line_gap
        return self.hhea_ascender - self.hhea_descender + self.hhea_line_gap


@dataclass(frozen=True)
class LicenseInfo:
    copyright: str | None
    license: str | None
    license_url: str | None
    reserved_font_names: tuple[str, ...] = ()
    """OFL Reserved Font Names: a modified font must not use these in its name."""


@dataclass(frozen=True)
class FontProfile:
    """Read-only facts about a font. Produced by the Inspector."""

    family_name: str
    upm: int
    glyph_count: int
    codepoints: frozenset[int]
    outline: OutlineFormat
    metrics: VerticalMetrics
    x_height: int | None
    cap_height: int | None
    ideo_embox: tuple[int, int] | None
    """(bottom, top) of the ideographic em box, in font units, when known."""
    ideo_char_face: tuple[int, int] | None
    """(bottom, top) of the ideographic character face (BASE icfb/icft), when known."""
    has_vertical_metrics: bool
    features: frozenset[str]
    scripts: frozenset[str]
    """OpenType script tags in GSUB/GPOS (e.g. ``latn``, ``hani``)."""
    fs_type: int
    license: LicenseInfo


@dataclass(frozen=True)
class RouteDecision:
    codepoint: int
    source: Source
    rule: str
    """Name of the rule that decided, e.g. ``"default:cjk-unified"`` or ``"override"``."""


@dataclass(frozen=True)
class AssignmentPlan:
    """Which source font supplies each codepoint. Produced by the Script Router."""

    western: frozenset[int]
    cjk: frozenset[int]
    missing: frozenset[int] = frozenset()
    """Covered by an input font but not assigned (only when fallback is off)."""
    excluded: frozenset[int] = frozenset()
    """Left out on purpose by the config (e.g. Hangul when ``include_hangul`` is off)."""
    decisions: tuple[RouteDecision, ...] = ()

    def __post_init__(self) -> None:
        overlap = self.western & self.cjk
        if overlap:
            sample = ", ".join(f"U+{cp:04X}" for cp in sorted(overlap)[:5])
            raise ValueError(f"codepoints assigned to both fonts: {sample}")
        assigned = self.western | self.cjk
        if self.missing & assigned:
            raise ValueError("a codepoint cannot be both assigned and missing")
        if self.excluded & (assigned | self.missing):
            raise ValueError("an excluded codepoint cannot be assigned or missing")

    def decision_for(self, codepoint: int) -> RouteDecision | None:
        for d in self.decisions:
            if d.codepoint == codepoint:
                return d
        return None

    def source_of(self, codepoint: int) -> Source | None:
        if codepoint in self.western:
            return Source.WESTERN
        if codepoint in self.cjk:
            return Source.CJK
        return None


@dataclass(frozen=True)
class NormalizePlan:
    """Concrete numbers for the Normalizer, derived from profiles + config."""

    target_upm: int
    target_outline: Literal["glyf", "CFF"]
    western_scale: float = 1.0
    western_baseline_shift: int = 0
    vertical_advance: int | None = None
    """Advance height for synthesized Western ``vmtx`` entries. ``None`` = no vertical
    metrics (the CJK font has none either)."""
    vertical_top: int | None = None
    """Top of the CJK ideographic em box: Western top side bearings are measured from it."""

    def __post_init__(self) -> None:
        if self.target_upm < 16 or self.target_upm > 16384:
            raise ValueError("target_upm must be between 16 and 16384")
        if self.western_scale <= 0:
            raise ValueError("western_scale must be positive")


@dataclass(frozen=True)
class SubsetOptions:
    layout_features: tuple[str, ...] = ("*",)
    """OpenType features to keep; ``"*"`` = all (fontTools' default drops many, e.g. smcp)."""
    keep_hinting: bool = False
    """TrueType hinting is dropped by default: it would be wrong after scaling."""
    keep_legacy_kern: bool = True
    """Keep the old-style ``kern`` table (fontTools drops it by default)."""
    drop_tables: tuple[str, ...] = ("STAT",)
    """Extra tables to drop. STAT describes the source family's axes, which no longer apply."""


@dataclass(frozen=True)
class MergeOptions:
    base: Source = Source.CJK
    """The font whose whole-font tables (head, OS/2, BASE, vhea, gasp) the merge starts from."""
    glyph_name_suffix: str = ".cjk"
    """Appended to CJK glyph names that clash with Western glyph names, so the Western
    glyphs keep their standard names (A, a, one)."""


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str
    codepoint: int | None = None
    glyph: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    """Numbers and examples behind ``message``, so a UI can word it in other languages."""


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[Issue, ...] = ()
    glyph_count: int = 0
    coverage: dict[Source, int] = field(default_factory=dict)

    def by_severity(self, severity: Severity) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is severity)

    @property
    def has_errors(self) -> bool:
        return any(i.severity is Severity.ERROR for i in self.issues)

    def blocks_output(self, strict: bool = False) -> bool:
        """True when no font should be written: errors, or warnings in strict mode."""
        if self.has_errors:
            return True
        return strict and any(i.severity is Severity.WARNING for i in self.issues)


@dataclass(frozen=True)
class MergeResult:
    outputs: tuple[Path, ...]
    report: ValidationReport
    preview: Path | None = None
