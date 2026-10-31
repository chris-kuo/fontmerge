"""Stage 6: Validator."""

from __future__ import annotations

import builtins
from typing import Any

import pytest

from fontmerge import validate as validate_mod
from fontmerge.models import Severity, Source, ValidationReport
from fontmerge.validate import format_report, validate


def codes(report: ValidationReport, severity: Severity | None = None) -> set[str]:
    return {i.code for i in report.issues if severity is None or i.severity is severity}


def check(m: dict[str, Any], **kw: Any) -> ValidationReport:
    return validate(m["font"], m["route"], (m["western"], m["cjk"]), **kw)


def test_clean_merge_has_no_errors_or_warnings(small_merge: dict[str, Any]) -> None:
    report = check(small_merge)
    assert not codes(report, Severity.ERROR)
    assert not codes(report, Severity.WARNING)
    route = small_merge["route"]
    assert report.coverage == {Source.WESTERN: len(route.western), Source.CJK: len(route.cjk)}
    assert report.glyph_count == len(small_merge["font"].getGlyphOrder())


def test_unmapped_character(small_merge: dict[str, Any]) -> None:
    for table in small_merge["font"]["cmap"].tables:
        table.cmap.pop(0x4E00, None)
    report = check(small_merge)
    assert "unmapped" in codes(report, Severity.ERROR)
    assert report.blocks_output()


def test_wrong_source_detected(small_merge: dict[str, Any]) -> None:
    font = small_merge["font"]
    for table in font["cmap"].tables:
        if 0x41 in table.cmap:
            table.cmap[0x41] = "uni4E00"  # point 'A' at a CJK glyph
    issue = next(i for i in check(small_merge).issues if i.code == "wrong-source")
    assert issue.severity is Severity.ERROR
    assert issue.codepoint == 0x41


def test_source_check_optional(small_merge: dict[str, Any]) -> None:
    report = validate(small_merge["font"], small_merge["route"])
    assert "wrong-source" not in codes(report)


def test_unplanned_character_warns(small_merge: dict[str, Any]) -> None:
    for table in small_merge["font"]["cmap"].tables:
        table.cmap[0xE000] = "A"  # a private-use character nobody planned
    assert "unplanned" in codes(check(small_merge), Severity.WARNING)


def test_glyph_limit(small_merge: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate_mod, "MAX_GLYPHS", 5)
    assert "glyph-limit" in codes(check(small_merge), Severity.ERROR)


def test_empty_glyph_warns(small_merge: dict[str, Any]) -> None:
    font = small_merge["font"]
    for table in font["cmap"].tables:
        if 0x42 in table.cmap:
            table.cmap[0x42] = "space"
    report = validate(font, small_merge["route"])
    issue = next(i for i in report.issues if i.code == "empty-glyph")
    assert issue.severity is Severity.WARNING and issue.codepoint == 0x42


def test_space_is_not_reported_empty(small_merge: dict[str, Any]) -> None:
    assert "empty-glyph" not in codes(check(small_merge))


def test_clipping_warns(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["OS/2"].usWinAscent = 100
    assert "clipping" in codes(check(small_merge), Severity.WARNING)


def test_tall_western_glyphs_noted(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["OS/2"].sTypoAscender = 600
    small_merge["font"]["hhea"].ascent = 600
    issue = next(i for i in check(small_merge).issues if i.code == "tall-glyphs")
    assert issue.severity is Severity.INFO
    assert "Western characters" in issue.message


def test_bad_line_metrics(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["OS/2"].sTypoAscender = 0
    assert "line-metrics" in codes(check(small_merge), Severity.ERROR)


def test_differing_hhea_noted(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["hhea"].lineGap = 100
    assert "line-metrics-differ" in codes(check(small_merge), Severity.INFO)


def test_incomplete_vertical_metrics(small_merge: dict[str, Any]) -> None:
    del small_merge["font"]["vmtx"].metrics["A"]
    issue = next(i for i in check(small_merge).issues if i.code == "vertical")
    assert issue.severity is Severity.ERROR and issue.glyph == "A"


def test_vertical_tables_must_pair(small_merge: dict[str, Any]) -> None:
    del small_merge["font"]["vhea"]
    assert "vertical" in codes(check(small_merge), Severity.ERROR)


@pytest.mark.parametrize("ps_name", ["Has Space-Regular", "Bad(Name)", "X" * 64])
def test_bad_postscript_name(small_merge: dict[str, Any], ps_name: str) -> None:
    small_merge["font"]["name"].setName(ps_name, 6, 3, 1, 0x409)
    assert "names" in codes(check(small_merge), Severity.ERROR)


def test_missing_required_name(small_merge: dict[str, Any]) -> None:
    name = small_merge["font"]["name"]
    name.names = [n for n in name.names if n.nameID != 4]
    assert "names" in codes(check(small_merge), Severity.ERROR)


def test_ots_skipped_when_not_installed(
    small_merge: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_import = builtins.__import__

    def no_ots(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "ots":
            raise ImportError
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ots)
    issue = next(i for i in check(small_merge).issues if i.code == "ots-skipped")
    assert issue.severity is Severity.INFO
    assert "opentype-sanitizer" in issue.message


def test_ots_can_be_turned_off(small_merge: dict[str, Any]) -> None:
    assert not {"ots", "ots-skipped"} & codes(check(small_merge, run_ots=False))


def test_issues_sorted_by_severity(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["OS/2"].usWinAscent = 100  # warning
    small_merge["font"]["OS/2"].sTypoAscender = 0  # error
    severities = [i.severity for i in check(small_merge).issues]
    rank = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    assert severities == sorted(severities, key=rank.__getitem__)


def test_format_report(small_merge: dict[str, Any]) -> None:
    small_merge["font"]["OS/2"].usWinAscent = 100
    text = format_report(check(small_merge))
    assert text.startswith("Glyphs: ")
    assert "from the western font" in text and "from the cjk font" in text
    assert "1 warnings" in text
    assert "[warning] clipping:" in text


# Real fonts -----------------------------------------------------------------------------


@pytest.mark.realfont
def test_real_font_is_valid(real_merge: dict[str, Any]) -> None:
    report = validate(
        real_merge["font"], real_merge["route"], (real_merge["western"], real_merge["cjk"])
    )
    assert not report.blocks_output(strict=True)
    assert report.coverage == {Source.WESTERN: 1147, Source.CJK: 12154}
    tall = next(i for i in report.issues if i.code == "tall-glyphs")
    assert tall.message.startswith("35 Western characters")
