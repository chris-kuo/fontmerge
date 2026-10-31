"""Stage 0: shared data models and error types."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fontmerge.errors import FontMergeError, GlyphLimitError
from fontmerge.models import (
    AssignmentPlan,
    Issue,
    MergeConfig,
    NamingConfig,
    NormalizeConfig,
    NormalizePlan,
    OutputConfig,
    PunctuationPolicy,
    RangeOverride,
    RoutingConfig,
    Severity,
    Source,
    SourceSpec,
    ValidationReport,
)


def _config(**overrides: object) -> MergeConfig:
    data: dict[str, object] = {
        "western": {"path": "Latin.ttf"},
        "cjk": {"path": "CJK.ttc", "face": "Noto Sans CJK JP"},
        "output": {"path": "Merged.otf"},
        "naming": {"family": "My Merged"},
    }
    data.update(overrides)
    return MergeConfig.model_validate(data)


# Config models ------------------------------------------------------------------------


def test_minimal_config_gets_defaults() -> None:
    cfg = _config()
    assert cfg.western.path == Path("Latin.ttf")
    assert cfg.cjk.face == "Noto Sans CJK JP"
    assert cfg.routing.punctuation is PunctuationPolicy.SPLIT
    assert cfg.routing.include_hangul is False
    assert cfg.normalize.target_outline == "auto"
    assert cfg.naming.style == "Regular"


def test_config_is_frozen() -> None:
    cfg = _config()
    with pytest.raises(ValidationError):
        cfg.naming = NamingConfig(family="Other")  # type: ignore[misc]


def test_unknown_config_key_rejected() -> None:
    with pytest.raises(ValidationError, match="extra"):
        _config(colour="blue")


@pytest.mark.parametrize("face", [-1, "  "])
def test_bad_face_rejected(face: object) -> None:
    with pytest.raises(ValidationError):
        SourceSpec(path=Path("a.ttc"), face=face)  # type: ignore[arg-type]


def test_range_override_must_be_ordered() -> None:
    RangeOverride(start=0x2000, end=0x206F, source=Source.WESTERN)
    with pytest.raises(ValidationError, match="after end"):
        RangeOverride(start=0x3000, end=0x2000, source=Source.CJK)


def test_range_override_bounded_to_unicode() -> None:
    with pytest.raises(ValidationError):
        RangeOverride(start=0, end=0x110000, source=Source.CJK)


def test_routing_overrides_parse_from_dicts() -> None:
    cfg = RoutingConfig.model_validate(
        {"punctuation": "cjk", "overrides": [{"start": 0x2010, "end": 0x2027, "source": "cjk"}]}
    )
    assert cfg.punctuation is PunctuationPolicy.CJK
    assert cfg.overrides[0].source is Source.CJK


def test_western_scale_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        NormalizeConfig(western_scale=0)


@pytest.mark.parametrize("version", ["1.0", "v1.000", "1.0000"])
def test_naming_version_format(version: str) -> None:
    with pytest.raises(ValidationError):
        NamingConfig(family="X", version=version)


def test_vendor_id_max_four_chars() -> None:
    with pytest.raises(ValidationError):
        NamingConfig(family="X", vendor_id="TOOLONG")


def test_output_suffix_checked() -> None:
    with pytest.raises(ValidationError, match=r"\.ttf"):
        OutputConfig(path=Path("out.pdf"))


def test_output_formats_resolved_from_suffix() -> None:
    assert OutputConfig(path=Path("a.otf")).resolved_formats() == ("otf",)
    out = OutputConfig(path=Path("a.TTF"), formats=("woff2", "ttf"))
    assert out.resolved_formats() == ("ttf", "woff2")


# Runtime models -----------------------------------------------------------------------


def test_assignment_plan_lookup() -> None:
    plan = AssignmentPlan(
        western=frozenset({0x41}), cjk=frozenset({0x4E00}), missing=frozenset({1})
    )
    assert plan.source_of(0x41) is Source.WESTERN
    assert plan.source_of(0x4E00) is Source.CJK
    assert plan.source_of(0x42) is None


def test_assignment_plan_rejects_overlap() -> None:
    with pytest.raises(ValueError, match="U\\+0041"):
        AssignmentPlan(western=frozenset({0x41}), cjk=frozenset({0x41}))


def test_assignment_plan_rejects_assigned_and_missing() -> None:
    with pytest.raises(ValueError):
        AssignmentPlan(western=frozenset({0x41}), cjk=frozenset(), missing=frozenset({0x41}))


def test_normalize_plan_bounds() -> None:
    NormalizePlan(target_upm=1000, target_outline="CFF")
    with pytest.raises(ValueError):
        NormalizePlan(target_upm=0, target_outline="glyf")
    with pytest.raises(ValueError):
        NormalizePlan(target_upm=1000, target_outline="glyf", western_scale=0)


def test_validation_report_severity() -> None:
    warn = Issue(Severity.WARNING, "metrics", "line gap differs")
    err = Issue(Severity.ERROR, "glyph-limit", "too many glyphs")
    ok = ValidationReport(issues=(warn,))
    assert not ok.has_errors
    assert not ok.blocks_output()
    assert ok.blocks_output(strict=True)
    bad = ValidationReport(issues=(warn, err))
    assert bad.has_errors
    assert bad.by_severity(Severity.ERROR) == (err,)


# Errors -------------------------------------------------------------------------------


def test_error_carries_hint() -> None:
    e = GlyphLimitError("70,000 glyphs", hint="drop Hangul with include_hangul=false")
    assert isinstance(e, FontMergeError)
    assert e.message == "70,000 glyphs"
    assert "include_hangul" in str(e)
    assert str(FontMergeError("plain")) == "plain"
