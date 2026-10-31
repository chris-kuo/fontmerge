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
from typing import TYPE_CHECKING, Literal

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


class RangeOverride(_Frozen):
    """Force an inclusive codepoint range to a source font."""

    start: int = Field(ge=0, le=MAX_CODEPOINT)
    end: int = Field(ge=0, le=MAX_CODEPOINT)
    source: Source

    @model_validator(mode="after")
    def _ordered(self) -> RangeOverride:
        if self.start > self.end:
            raise ValueError(f"range start U+{self.start:04X} is after end U+{self.end:04X}")
        return self


class RoutingConfig(_Frozen):
    include_hangul: bool = False
    punctuation: PunctuationPolicy = PunctuationPolicy.SPLIT
    overrides: tuple[RangeOverride, ...] = ()


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


OutputFormat = Literal["ttf", "otf", "woff2"]


class OutputConfig(_Frozen):
    path: Path
    formats: tuple[OutputFormat, ...] = ()
    """Extra formats to write. Empty = infer one format from ``path``'s suffix."""
    write_report: bool = True
    preview: bool = False
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


# --------------------------------------------------------------------------------------
# Runtime models
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class FontSource:
    """A loaded font face. Produced by the Loader."""

    path: Path
    face_index: int
    ttfont: TTFont
    outline: OutlineFormat
    is_variable: bool


@dataclass(frozen=True)
class FontProfile:
    """Read-only facts about a font. Produced by the Inspector."""

    upm: int
    glyph_count: int
    codepoints: frozenset[int]
    outline: OutlineFormat
    ascender: int
    descender: int
    line_gap: int
    x_height: int | None
    cap_height: int | None
    ideo_embox: tuple[int, int] | None
    """(bottom, top) of the ideographic em box, in font units, when known."""
    has_vertical_metrics: bool
    features: frozenset[str]
    fs_type: int
    family_name: str


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
    decisions: tuple[RouteDecision, ...] = ()

    def __post_init__(self) -> None:
        overlap = self.western & self.cjk
        if overlap:
            sample = ", ".join(f"U+{cp:04X}" for cp in sorted(overlap)[:5])
            raise ValueError(f"codepoints assigned to both fonts: {sample}")
        if self.missing & (self.western | self.cjk):
            raise ValueError("a codepoint cannot be both assigned and missing")

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
    """Advance height for synthesized Western ``vmtx`` entries. ``None`` = target UPM."""

    def __post_init__(self) -> None:
        if self.target_upm < 16 or self.target_upm > 16384:
            raise ValueError("target_upm must be between 16 and 16384")
        if self.western_scale <= 0:
            raise ValueError("western_scale must be positive")


@dataclass(frozen=True)
class MergeOptions:
    base: Source = Source.CJK
    glyph_name_suffix: str = ".w"
    """Appended to Western glyph names that clash with CJK glyph names."""


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
