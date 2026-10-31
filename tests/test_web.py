"""W1: bytes-in, bytes-out adapter used by the browser version."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from fontmerge.errors import ConfigError, FontMergeError
from fontmerge.web import (
    error_to_dict,
    inspect_bytes,
    merge_bytes,
    output_filename,
    version,
)


def read(path: Path) -> bytes:
    return path.read_bytes()


def test_version() -> None:
    assert version() == "0.1.0"


def test_merge_bytes(latin_ttf: Path, cjk_otf: Path) -> None:
    messages: list[str] = []
    result = merge_bytes(
        read(latin_ttf),
        read(cjk_otf),
        {"naming": {"family": "Web Test", "style": "Light"}},
        messages.append,
    )
    assert result["filename"] == "WebTest-Light.ttf"
    assert result["format"] == "ttf"
    assert result["seconds"] >= 0
    font = TTFont(BytesIO(result["font"]))
    assert font["name"].getDebugName(1) == "Web Test Light"
    assert (
        len(font.getBestCmap())
        == result["report"]["coverage"]["western"] + result["report"]["coverage"]["cjk"]
    )
    assert messages[0].endswith("Loading fonts") and messages[-1].endswith("Done")


def test_merge_bytes_matches_cli(latin_ttf: Path, cjk_otf: Path, tmp_path: Path) -> None:
    from fontmerge.cli import main

    out = tmp_path / "cli.ttf"
    assert (
        main(
            [
                "--western",
                str(latin_ttf),
                "--cjk",
                str(cjk_otf),
                "-o",
                str(out),
                "--family",
                "Same",
                "--outline",
                "glyf",
                "-q",
            ]
        )
        == 0
    )
    web = merge_bytes(
        read(latin_ttf),
        read(cjk_otf),
        {"naming": {"family": "Same"}, "normalize": {"target_outline": "glyf"}},
    )
    a, b = TTFont(str(out)), TTFont(BytesIO(web["font"]))
    assert a.getGlyphOrder() == b.getGlyphOrder()
    assert a.getBestCmap() == b.getBestCmap()
    assert a["hmtx"].metrics == b["hmtx"].metrics


def test_settings_reach_the_config(latin_ttf: Path, cjk_otf: Path) -> None:
    result = merge_bytes(
        read(latin_ttf),
        read(cjk_otf),
        {
            "naming": {"family": "Scaled"},
            "normalize": {"western_scale": 0.5},
            "metrics": {"line_height": "max"},
            "format": "otf",
        },
    )
    assert result["filename"] == "Scaled-Regular.otf"
    font = TTFont(BytesIO(result["font"]))
    assert font["hmtx"]["H"][0] == round(round(1300 * 1000 / 2048) * 0.5)  # UPM, then scale
    assert font["OS/2"].sTypoAscender == 880  # "max": the CJK ascender is the larger


def test_collection_face(latin_ttf: Path, cjk_ttc: Path) -> None:
    result = merge_bytes(
        read(latin_ttf), read(cjk_ttc), {"naming": {"family": "F"}, "cjk_face": "Test CJK JP"}
    )
    assert "Test CJK JP" in str(result["report"]["issues"])


def test_collection_without_face_is_an_error(latin_ttf: Path, cjk_ttc: Path) -> None:
    with pytest.raises(ConfigError, match="2 faces"):
        merge_bytes(read(latin_ttf), read(cjk_ttc), {"naming": {"family": "F"}})


def test_family_required(latin_ttf: Path, cjk_otf: Path) -> None:
    with pytest.raises(ConfigError, match="family name"):
        merge_bytes(read(latin_ttf), read(cjk_otf), {})


def test_bad_setting_named(latin_ttf: Path, cjk_otf: Path) -> None:
    with pytest.raises(ConfigError, match=r"normalize\.western_scale"):
        merge_bytes(
            read(latin_ttf),
            read(cjk_otf),
            {"naming": {"family": "F"}, "normalize": {"western_scale": -1}},
        )


def test_bad_format(latin_ttf: Path, cjk_otf: Path) -> None:
    with pytest.raises(ConfigError, match="format"):
        merge_bytes(read(latin_ttf), read(cjk_otf), {"naming": {"family": "F"}, "format": "pdf"})


def test_garbage_input(cjk_otf: Path) -> None:
    with pytest.raises(FontMergeError):
        merge_bytes(b"not a font" * 50, read(cjk_otf), {"naming": {"family": "F"}})


def test_unsafe_file_names_are_harmless(latin_ttf: Path, cjk_otf: Path) -> None:
    result = merge_bytes(
        read(latin_ttf),
        read(cjk_otf),
        {"naming": {"family": "F"}},
        western_name="../../etc/passwd",
        cjk_name="a b/c?.otf",
    )
    assert result["font"][:4] in (b"\x00\x01\x00\x00", b"OTTO")


def test_inspect_bytes_single(latin_ttf: Path) -> None:
    info = inspect_bytes(read(latin_ttf), name="TestLatin.ttf")
    assert info["faces"] == [{"index": 0, "name": "Test Latin Regular", "family": "Test Latin"}]
    p = info["profile"]
    assert p["family"] == "Test Latin" and p["upm"] == 2048
    assert p["coverage"]["latin"] > 50 and p["coverage"]["han"] == 0
    assert all(i["severity"] == "info" for i in p["as_western"])
    assert any(i["code"] == "role-coverage" for i in p["as_cjk"])


def test_inspect_bytes_collection(cjk_ttc: Path) -> None:
    info = inspect_bytes(read(cjk_ttc))
    assert [f["family"] for f in info["faces"]] == ["Test CJK SC", "Test CJK JP"]
    assert info["profile"] is None
    chosen = inspect_bytes(read(cjk_ttc), face=1)
    assert chosen["profile"]["family"] == "Test CJK JP"
    assert chosen["selected_face"] == 1


def test_error_to_dict() -> None:
    assert error_to_dict(ConfigError("bad", hint="fix it")) == {
        "kind": "ConfigError",
        "message": "bad",
        "hint": "fix it",
    }
    assert error_to_dict(ValueError("x"))["kind"] == "ValueError"


@pytest.mark.parametrize(
    ("family", "style", "fmt", "expected"),
    [
        ("Iansui Literata", "Light", "ttf", "IansuiLiterata-Light.ttf"),
        ("芫荽", "Regular", "woff2", "Merged-Regular.woff2"),
        ("A-B C", "Semi Bold", "otf", "ABC-SemiBold.otf"),
    ],
)
def test_output_filename(family: str, style: str, fmt: str, expected: str) -> None:
    assert output_filename(family, style, fmt) == expected


@pytest.mark.realfont
def test_real_merge_bytes(literata: Path, iansui: Path) -> None:
    result = merge_bytes(
        read(literata),
        read(iansui),
        {
            "naming": {"family": "Iansui Literata", "style": "Light"},
            "normalize": {"western_scale": 0.96},
        },
    )
    font = TTFont(BytesIO(result["font"]))
    assert len(font.getBestCmap()) == 13301
    assert result["report"]["coverage"] == {"western": 1147, "cjk": 12154}
    assert result["filename"] == "IansuiLiterata-Light.ttf"


# W2: suggestions, reserved names, overrides, collection hint -----------------------------


def test_inspect_reports_style(latin_ttf: Path) -> None:
    assert inspect_bytes(read(latin_ttf))["profile"]["style"] == "Regular"


def test_suggest_matches_cli_auto_scale(latin_ttf: Path, cjk_otf: Path) -> None:
    from fontmerge.inspector import inspect_font
    from fontmerge.loader import load_font
    from fontmerge.normalize import auto_western_scale
    from fontmerge.web import suggest

    w = inspect_bytes(read(latin_ttf))["profile"]
    c = inspect_bytes(read(cjk_otf))["profile"]
    s = suggest(w, c)
    assert s["family"] == "Test CJK Test Latin"
    assert s["style"] == "Regular"
    expected = auto_western_scale(
        inspect_font(load_font(latin_ttf)), inspect_font(load_font(cjk_otf))
    )
    assert s["scale_exact"] == expected
    assert s["scale"] == round(expected, 2)
    assert s["reserved_conflicts"] == []


def test_suggest_flags_reserved_names(latin_ttf: Path, cjk_otf: Path) -> None:
    from fontmerge.web import suggest

    w = {**inspect_bytes(read(latin_ttf))["profile"], "reserved_font_names": ["Test Latin"]}
    c = inspect_bytes(read(cjk_otf))["profile"]
    assert suggest(w, c)["reserved_conflicts"] == ["Test Latin"]


@pytest.mark.parametrize(
    ("family", "expected"),
    [("Iansui Literata", ["Literata"]), ("IansuiLITERATA", ["Literata"]), ("Iansui Serif", [])],
)
def test_reserved_conflicts(family: str, expected: list[str]) -> None:
    from fontmerge.web import reserved_conflicts

    assert reserved_conflicts(family, ["Literata"]) == expected


def test_overrides_as_text(latin_ttf: Path, cjk_otf: Path) -> None:
    result = merge_bytes(
        read(latin_ttf),
        read(cjk_otf),
        {"naming": {"family": "F"}, "routing": {"overrides": ["U+0041=cjk"]}},
    )
    font = TTFont(BytesIO(result["font"]))
    assert font["hmtx"][font.getBestCmap()[0x41]][0] == 650  # the CJK test font's 'A'


def test_collection_hint_fits_the_page(latin_ttf: Path, cjk_ttc: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        merge_bytes(read(latin_ttf), read(cjk_ttc), {"naming": {"family": "F"}})
    assert exc.value.hint == "pick a face from the menu under the CJK font"


@pytest.mark.realfont
def test_real_suggestion_is_the_chosen_setup(literata: Path, iansui: Path) -> None:
    from fontmerge.web import suggest

    s = suggest(inspect_bytes(read(literata))["profile"], inspect_bytes(read(iansui))["profile"])
    assert (s["family"], s["style"], s["scale"]) == ("Iansui Literata", "Light", 0.96)


def test_strict_setting(latin_ttf: Path, cjk_otf: Path) -> None:
    from fontmerge.errors import ValidationFailedError

    # The tiny CJK test font triggers a coverage warning, which strict mode refuses.
    with pytest.raises(ValidationFailedError, match="role-coverage"):
        merge_bytes(read(latin_ttf), read(cjk_otf), {"naming": {"family": "F"}, "strict": True})
