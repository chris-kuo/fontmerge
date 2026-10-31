"""Stage 7: config loading (TOML file + command-line values)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fontmerge.config import load_config, parse_face, parse_override
from fontmerge.errors import ConfigError
from fontmerge.models import PunctuationPolicy, RangeOverride, Source

MINIMAL = """
[western]
path = "fonts/Latin.ttf"
[cjk]
path = "fonts/CJK.ttc"
face = "Test CJK JP"
[output]
path = "out/Merged.ttf"
[naming]
family = "Test Merged"
"""


def write(tmp_path: Path, text: str, name: str = "merge.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_toml_paths_resolved_from_the_file(tmp_path: Path) -> None:
    cfg = load_config({}, write(tmp_path / "", MINIMAL))
    assert cfg.western.path == tmp_path / "fonts" / "Latin.ttf"
    assert cfg.output.path == tmp_path / "out" / "Merged.ttf"
    assert cfg.cjk.face == "Test CJK JP"


def test_paths_normalized(tmp_path: Path) -> None:
    sub = tmp_path / "configs"
    sub.mkdir()
    cfg = load_config({}, write(sub, MINIMAL.replace('"out/', '"../out/')))
    assert cfg.output.path == tmp_path / "out" / "Merged.ttf"  # no "configs/.." left


def test_absolute_paths_kept(tmp_path: Path) -> None:
    text = MINIMAL.replace('"fonts/Latin.ttf"', '"/abs/Latin.ttf"')
    assert load_config({}, write(tmp_path, text)).western.path == Path("/abs/Latin.ttf")


def test_cli_overrides_file(tmp_path: Path) -> None:
    cli = {
        "naming": {"family": "From CLI", "style": None},
        "normalize": {"western_scale": 0.96},
        "routing": {"punctuation": "cjk"},
    }
    cfg = load_config(cli, write(tmp_path, MINIMAL + "[normalize]\nwestern_scale = 1.1\n"))
    assert cfg.naming.family == "From CLI"
    assert cfg.naming.style == "Regular"  # None never overrides
    assert cfg.normalize.western_scale == 0.96
    assert cfg.routing.punctuation is PunctuationPolicy.CJK


def test_cli_only(tmp_path: Path) -> None:
    cfg = load_config(
        {
            "western": {"path": tmp_path / "a.ttf"},
            "cjk": {"path": tmp_path / "b.otf", "face": None},
            "output": {"path": tmp_path / "o.otf"},
            "naming": {"family": "X"},
        }
    )
    assert cfg.output.path == tmp_path / "o.otf"
    assert cfg.cjk.face is None


def test_missing_settings_named_with_hints(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config({"western": {"path": tmp_path / "a.ttf"}})
    assert "cjk, output, naming" in exc.value.message
    assert exc.value.hint and "--family" in exc.value.hint and "--cjk" in exc.value.hint


def test_validation_errors_name_the_setting(tmp_path: Path) -> None:
    text = MINIMAL + "[normalize]\nwestern_scale = -1\n[metrics]\nline_height = 'huge'\n"
    with pytest.raises(ConfigError) as exc:
        load_config({}, write(tmp_path, text))
    assert "normalize.western_scale" in exc.value.message
    assert "metrics.line_height" in exc.value.message


def test_unknown_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"naming\.colour"):
        load_config({}, write(tmp_path, MINIMAL + 'colour = "blue"\n'))


def test_bad_toml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config({}, write(tmp_path, "[western\npath = 1"))


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config({}, tmp_path / "nope.toml")


def test_overrides_in_toml_accept_hex_and_u_plus(tmp_path: Path) -> None:
    text = MINIMAL + (
        '[[routing.overrides]]\nstart = 0x2018\nend = "U+201D"\nsource = "cjk"\n'
        '[[routing.overrides]]\nstart = "00B7"\nend = "00B7"\nsource = "western"\n'
    )
    cfg = load_config({}, write(tmp_path, text))
    assert cfg.routing.overrides == (
        RangeOverride(start=0x2018, end=0x201D, source=Source.CJK),
        RangeOverride(start=0xB7, end=0xB7, source=Source.WESTERN),
    )


def test_bad_codepoint_string(tmp_path: Path) -> None:
    text = MINIMAL + '[[routing.overrides]]\nstart = "U+ZZZZ"\nend = "U+2000"\nsource = "cjk"\n'
    with pytest.raises(ConfigError, match="not a codepoint"):
        load_config({}, write(tmp_path, text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("U+2018-U+201D=cjk", {"start": "U+2018", "end": "U+201D", "source": "cjk"}),
        ("U+00B7=western", {"start": "U+00B7", "end": "U+00B7", "source": "western"}),
        (" 2010 - 2015 = cjk ", {"start": "2010", "end": "2015", "source": "cjk"}),
    ],
)
def test_parse_override(text: str, expected: dict[str, str]) -> None:
    assert parse_override(text) == expected


def test_parse_override_needs_equals() -> None:
    with pytest.raises(ConfigError) as exc:
        parse_override("U+2018-U+201D")
    assert exc.value.hint and "START-END=SOURCE" in exc.value.hint


@pytest.mark.parametrize(
    ("value", "expected"), [(None, None), ("1", 1), (" 0 ", 0), ("Test CJK JP", "Test CJK JP")]
)
def test_parse_face(value: str | None, expected: int | str | None) -> None:
    assert parse_face(value) == expected


@pytest.mark.realfont
def test_example_config_loads() -> None:
    root = Path(__file__).parent.parent
    cfg = load_config({}, root / "examples" / "iansui-literata.toml")
    assert cfg.western.path == root / "tests" / "realfonts" / "Literata-Light.ttf"
    assert cfg.western.path.exists() and cfg.cjk.path.exists()
    assert (cfg.naming.family, cfg.naming.style) == ("Iansui Literata", "Light")
    assert cfg.normalize.western_scale == 0.96
    assert cfg.metrics.line_height == "cjk"
