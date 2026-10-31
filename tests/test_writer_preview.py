"""Stage 6: Writer and Previewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fontTools.ttLib import TTFont

from fontmerge import writer as writer_mod
from fontmerge.errors import ConfigError, ValidationFailedError
from fontmerge.models import Issue, OutputConfig, Severity, ValidationReport
from fontmerge.preview import render_preview
from fontmerge.validate import validate
from fontmerge.writer import output_paths, report_path, woff2_available, write_outputs


def report_for(m: dict[str, Any]) -> ValidationReport:
    return validate(m["font"], m["route"], (m["western"], m["cjk"]), run_ots=False)


WARNING = ValidationReport(issues=(Issue(Severity.WARNING, "clipping", "too tall"),))
ERROR = ValidationReport(issues=(Issue(Severity.ERROR, "unmapped", "missing"),))


# Writer ---------------------------------------------------------------------------------


def test_writes_font_and_report(small_merge: dict[str, Any], tmp_path: Path) -> None:
    cfg = OutputConfig(path=tmp_path / "out" / "Merged.ttf")
    written = write_outputs(small_merge["font"], report_for(small_merge), cfg)
    assert written == [tmp_path / "out" / "Merged.ttf", tmp_path / "out" / "Merged.report.json"]
    font = TTFont(str(written[0]))
    assert font["name"].getDebugName(1) == "Test Merged"
    data = json.loads(written[1].read_text())
    assert data["has_errors"] is False
    assert data["glyph_count"] == len(font.getGlyphOrder())
    assert "summary" in data
    assert not list((tmp_path / "out").glob(".*"))  # no temp files left behind
    plain = tmp_path / "plain"
    plain.write_bytes(b"")
    assert written[0].stat().st_mode & 0o777 == plain.stat().st_mode & 0o777


def test_extra_formats(small_merge: dict[str, Any], tmp_path: Path) -> None:
    cfg = OutputConfig(path=tmp_path / "M.ttf", formats=("otf",), write_report=False)
    written = write_outputs(small_merge["font"], report_for(small_merge), cfg)
    assert written == [tmp_path / "M.ttf", tmp_path / "M.otf"]
    assert TTFont(str(written[1])).getBestCmap() == TTFont(str(written[0])).getBestCmap()


def test_output_paths_and_report_path(tmp_path: Path) -> None:
    cfg = OutputConfig(path=tmp_path / "A.otf", formats=("woff2",))
    assert output_paths(cfg) == {"otf": tmp_path / "A.otf", "woff2": tmp_path / "A.woff2"}
    assert report_path(cfg) == tmp_path / "A.report.json"


def test_errors_block_writing(small_merge: dict[str, Any], tmp_path: Path) -> None:
    cfg = OutputConfig(path=tmp_path / "M.ttf")
    with pytest.raises(ValidationFailedError, match="unmapped"):
        write_outputs(small_merge["font"], ERROR, cfg)
    assert not any(tmp_path.iterdir())


def test_warnings_block_only_in_strict_mode(small_merge: dict[str, Any], tmp_path: Path) -> None:
    write_outputs(small_merge["font"], WARNING, OutputConfig(path=tmp_path / "ok.ttf"))
    assert (tmp_path / "ok.ttf").exists()
    with pytest.raises(ValidationFailedError) as exc:
        write_outputs(
            small_merge["font"], WARNING, OutputConfig(path=tmp_path / "s.ttf", strict=True)
        )
    assert exc.value.hint and "--strict" in exc.value.hint
    assert not (tmp_path / "s.ttf").exists()


def test_woff2_needs_brotli(
    small_merge: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(writer_mod, "woff2_available", lambda: False)
    cfg = OutputConfig(path=tmp_path / "M.ttf", formats=("woff2",))
    with pytest.raises(ConfigError, match="brotli"):
        write_outputs(small_merge["font"], report_for(small_merge), cfg)
    assert not any(tmp_path.iterdir())  # nothing written, not even the TTF


@pytest.mark.skipif(not woff2_available(), reason="brotli not installed")
def test_woff2_written(small_merge: dict[str, Any], tmp_path: Path) -> None:
    cfg = OutputConfig(path=tmp_path / "M.woff2", write_report=False)
    (path,) = write_outputs(small_merge["font"], report_for(small_merge), cfg)
    assert TTFont(str(path)).flavor == "woff2"


# Previewer ------------------------------------------------------------------------------


@pytest.fixture
def saved_font(small_merge: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "fonts" / "Merged.ttf"
    path.parent.mkdir()
    small_merge["font"].save(str(path))
    return path


def test_html_preview(saved_font: Path, tmp_path: Path) -> None:
    out = render_preview(saved_font, tmp_path / "preview" / "index.html", samples=("A <b> & 一",))
    page = out.read_text(encoding="utf-8")
    assert 'src: url("../fonts/Merged.ttf")' in page  # relative to the page
    assert "A &lt;b&gt; &amp; 一" in page  # sample text is escaped
    assert "writing-mode: vertical-rl" in page
    assert "Test Merged" in page


def test_png_preview(saved_font: Path, tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    out = render_preview(saved_font, tmp_path / "p.png", samples=("AB 一",), vertical=())
    from PIL import Image

    with Image.open(out) as img:
        assert img.size[0] == 1500 and img.size[1] > 100


def test_png_preview_grows_to_fit_long_lines(saved_font: Path, tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    out = render_preview(saved_font, tmp_path / "wide.png", samples=("AB" * 200,), vertical=())
    from PIL import Image

    with Image.open(out) as img:
        assert img.size[0] > 1500


def test_unknown_preview_format(saved_font: Path, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\.html or \.png"):
        render_preview(saved_font, tmp_path / "p.pdf")


# Real fonts -----------------------------------------------------------------------------


@pytest.mark.realfont
def test_real_write_and_preview(real_merge: dict[str, Any], tmp_path: Path) -> None:
    report = validate(
        real_merge["font"], real_merge["route"], (real_merge["western"], real_merge["cjk"])
    )
    cfg = OutputConfig(path=tmp_path / "IansuiLiterata-Light.ttf")
    font_path, rp = write_outputs(real_merge["font"], report, cfg)
    assert font_path.stat().st_size > 5_000_000
    assert json.loads(rp.read_text())["coverage"] == {"western": 1147, "cjk": 12154}
    html = render_preview(font_path, tmp_path / "preview.html")
    assert "Iansui Literata Light" in html.read_text(encoding="utf-8")
