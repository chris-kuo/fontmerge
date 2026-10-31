"""Stage 7: Orchestrator and command line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from fontfactory import build_cjk_otf
from fontmerge.cli import main
from fontmerge.errors import UnsupportedFontError, ValidationFailedError
from fontmerge.inspector import FS_NO_SUBSETTING
from fontmerge.models import MergeConfig, Severity
from fontmerge.pipeline import run

ROOT = Path(__file__).parent.parent


def config(western: Path, cjk: Path, out: Path, **output: object) -> MergeConfig:
    return MergeConfig.model_validate(
        {
            "western": {"path": western},
            "cjk": {"path": cjk},
            "output": {"path": out, **output},
            "naming": {"family": "Test Merged", "style": "Light"},
        }
    )


# Orchestrator ---------------------------------------------------------------------------


def test_run_writes_font_and_report(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    messages: list[str] = []
    result = run(config(latin_ttf, cjk_otf, tmp_path / "M.otf"), messages.append)
    assert result.outputs == (tmp_path / "M.otf", tmp_path / "M.report.json")
    font = TTFont(str(result.outputs[0]))
    assert font["name"].getDebugName(1) == "Test Merged Light"
    assert "CFF " in font  # follows the CJK font's outlines
    assert result.preview is None
    assert messages[0].endswith("Loading fonts") and messages[-1].endswith("Done")
    assert all(m.startswith("[") for m in messages)  # timed


def test_inspector_issues_carried_into_report(
    latin_ttf: Path, cjk_otf: Path, tmp_path: Path
) -> None:
    # The tiny CJK test font has 3 Han characters, which the Inspector flags.
    result = run(config(latin_ttf, cjk_otf, tmp_path / "M.ttf"))
    warning = next(i for i in result.report.issues if i.code == "role-coverage")
    assert warning.severity is Severity.WARNING
    assert warning.message.startswith("CJK font: ")


def test_strict_refuses_but_writes_report(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    cfg = config(latin_ttf, cjk_otf, tmp_path / "M.ttf", strict=True)
    with pytest.raises(ValidationFailedError) as exc:
        run(cfg)
    assert "role-coverage" in exc.value.message
    assert exc.value.hint and "M.report.json" in exc.value.hint and "--strict" in exc.value.hint
    assert not (tmp_path / "M.ttf").exists()
    report = json.loads((tmp_path / "M.report.json").read_text())
    assert report["issues"][0]["code"] == "role-coverage"


def test_licence_error_stops_before_merging(latin_ttf: Path, tmp_path: Path) -> None:
    cjk = build_cjk_otf(tmp_path / "nosub.otf", fs_type=FS_NO_SUBSETTING)
    with pytest.raises(UnsupportedFontError, match="forbid subsetting"):
        run(config(latin_ttf, cjk, tmp_path / "M.ttf"))
    assert not any(p.suffix in {".ttf", ".json"} for p in tmp_path.iterdir())


def test_run_with_html_preview(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    result = run(config(latin_ttf, cjk_otf, tmp_path / "M.ttf", preview="html"))
    assert result.preview == tmp_path / "M.preview.html"
    assert 'url("M.ttf")' in result.preview.read_text(encoding="utf-8")


def test_run_selects_collection_face(latin_ttf: Path, cjk_ttc: Path, tmp_path: Path) -> None:
    cfg = MergeConfig.model_validate(
        {
            "western": {"path": latin_ttf},
            "cjk": {"path": cjk_ttc, "face": "Test CJK JP"},
            "output": {"path": tmp_path / "M.ttf"},
            "naming": {"family": "Test Merged"},
        }
    )
    assert "Test CJK JP" in run(cfg).report.issues[0].message  # role warning names the face


# Command line ---------------------------------------------------------------------------


def merge_args(latin: Path, cjk: Path, out: Path, *extra: str) -> list[str]:
    return [
        "--western",
        str(latin),
        "--cjk",
        str(cjk),
        "-o",
        str(out),
        "--family",
        "CLI Test",
        *extra,
    ]


def test_cli_merge(
    latin_ttf: Path, cjk_otf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "C.ttf"
    code = main(
        ["merge", *merge_args(latin_ttf, cjk_otf, out, "--style", "Bold", "--scale", "0.9")]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "Wrote:" in captured.out and str(out) in captured.out
    assert "Glyphs:" in captured.out
    assert "Loading fonts" in captured.err  # progress goes to stderr
    font = TTFont(str(out))
    assert font["name"].getDebugName(1) == "CLI Test"  # RIBBI: Bold keeps family in ID 1
    assert font["OS/2"].usWeightClass == 700


def test_cli_merge_is_default_command(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    assert main([*merge_args(latin_ttf, cjk_otf, tmp_path / "D.ttf", "-q")]) == 0
    assert (tmp_path / "D.ttf").exists()


def test_cli_quiet(
    latin_ttf: Path, cjk_otf: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(merge_args(latin_ttf, cjk_otf, tmp_path / "Q.ttf", "--quiet", "--no-report"))
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert not (tmp_path / "Q.report.json").exists()


def test_cli_options_reach_the_config(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    out = tmp_path / "O.ttf"
    args = merge_args(
        latin_ttf,
        cjk_otf,
        out,
        "-q",
        "--format",
        "otf",
        "--punctuation",
        "cjk",
        "--override",
        "U+0041-U+0041=cjk",
        "--line-height",
        "max",
        "--vendor",
        "ABCD",
        "--font-version",
        "2.500",
    )
    assert main(args) == 0
    font = TTFont(str(out))
    assert (tmp_path / "O.otf").exists()
    assert font["hmtx"][font.getBestCmap()[0x41]][0] == 650  # the CJK test font's 'A'
    assert font["hmtx"][font.getBestCmap()[0x2026]][0] == 1000  # the CJK font's ellipsis
    assert font["OS/2"].achVendID == "ABCD"
    assert font["name"].getDebugName(5) == "Version 2.500"


def test_cli_config_file_with_override(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    cfg = tmp_path / "m.toml"
    cfg.write_text(
        f'[western]\npath = "{latin_ttf}"\n[cjk]\npath = "{cjk_otf}"\n'
        '[output]\npath = "from-file.ttf"\n[naming]\nfamily = "From File"\n'
    )
    assert main(["-c", str(cfg), "--family", "From CLI", "-q"]) == 0
    font = TTFont(str(tmp_path / "from-file.ttf"))  # relative to the config file
    assert font["name"].getDebugName(1) == "From CLI"


def test_cli_error_exit_code_and_hint(
    latin_ttf: Path, cjk_ttc: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(merge_args(latin_ttf, cjk_ttc, tmp_path / "E.ttf"))
    assert code == 1
    err = capsys.readouterr().err
    assert "error: TestCJK.ttc contains 2 faces" in err
    assert "hint: set --cjk-face" in err


def test_cli_missing_settings(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["merge", "--family", "X"]) == 1
    assert "missing required settings" in capsys.readouterr().err


def test_cli_usage_errors_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["merge", "--line-height", "giant"])
    assert exc.value.code == 2


def test_cli_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage: fontmerge" in capsys.readouterr().out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "fontmerge 0.1.0" in capsys.readouterr().out


def test_cli_inspect(latin_ttf: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(latin_ttf)]) == 0
    out = capsys.readouterr().out
    assert "Test Latin" in out and "units per em: 2048" in out
    assert "as the western font: ok" in out
    assert "as the cjk font: issues" in out


def test_cli_inspect_collection(cjk_ttc: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(cjk_ttc)]) == 0
    assert "2 faces" in capsys.readouterr().out
    assert main(["inspect", str(cjk_ttc), "--face", "1"]) == 0
    assert "Test CJK JP" in capsys.readouterr().out


def test_python_dash_m(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "fontmerge", "--version"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=False,
    )
    assert proc.returncode == 0 and "fontmerge" in proc.stdout


# Real fonts, end to end -----------------------------------------------------------------


@pytest.mark.realfont
def test_real_cli_with_example_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "IansuiLiterata-Light.ttf"
    code = main(["-c", str(ROOT / "examples" / "iansui-literata.toml"), "-o", str(out)])
    assert code == 0
    captured = capsys.readouterr()
    assert "0 errors, 0 warnings" in captured.out
    font = TTFont(str(out))
    assert font["name"].getDebugName(1) == "Iansui Literata Light"
    assert len(font.getBestCmap()) == 13301
    assert font["OS/2"].sTypoAscender == 940
    assert (tmp_path / "IansuiLiterata-Light.preview.html").exists()
    report = json.loads((tmp_path / "IansuiLiterata-Light.report.json").read_text())
    assert report["coverage"] == {"western": 1147, "cjk": 12154}
