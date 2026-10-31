"""Stage 1: Font Loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from fontmerge.errors import ConfigError, FontLoadError, UnsupportedFontError
from fontmerge.loader import is_collection, list_faces, load_font


def test_load_ttf(latin_ttf: Path) -> None:
    src = load_font(latin_ttf)
    assert src.outline == "glyf"
    assert src.face_index == 0
    assert not src.is_collection and not src.is_variable
    assert src.face is not None and src.face.family == "Test Latin"
    assert src.ttfont.getBestCmap()[0x41] == "A"


def test_load_otf_detects_cff(cjk_otf: Path) -> None:
    src = load_font(cjk_otf)
    assert src.outline == "CFF"


def test_is_collection(cjk_ttc: Path, cjk_otf: Path) -> None:
    assert is_collection(cjk_ttc)
    assert not is_collection(cjk_otf)


def test_list_faces(cjk_ttc: Path, latin_ttf: Path) -> None:
    faces = list_faces(cjk_ttc)
    assert [f.index for f in faces] == [0, 1]
    assert [f.family for f in faces] == ["Test CJK SC", "Test CJK JP"]
    assert faces[1].postscript_name == "TestCJKJP-Regular"
    assert len(list_faces(latin_ttf)) == 1


def test_collection_face_by_index(cjk_ttc: Path) -> None:
    src = load_font(cjk_ttc, 1)
    assert src.is_collection
    assert src.face_index == 1
    assert src.ttfont["name"].getDebugName(1) == "Test CJK JP"


@pytest.mark.parametrize(
    "name", ["Test CJK JP", "test cjk jp", "TestCJKJP-Regular", "Test CJK JP Regular"]
)
def test_collection_face_by_name(cjk_ttc: Path, name: str) -> None:
    assert load_font(cjk_ttc, name).face_index == 1


def test_collection_without_face_lists_faces(cjk_ttc: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_font(cjk_ttc, option_name="--cjk-face")
    assert "2 faces" in exc.value.message
    assert exc.value.hint is not None
    assert "--cjk-face" in exc.value.hint and "Test CJK JP" in exc.value.hint


def test_collection_bad_index(cjk_ttc: Path) -> None:
    with pytest.raises(ConfigError, match="no face 5"):
        load_font(cjk_ttc, 5)


def test_unknown_face_name(cjk_ttc: Path) -> None:
    with pytest.raises(ConfigError, match="no face named 'Test CJK KR'"):
        load_font(cjk_ttc, "Test CJK KR")


def test_single_face_file_accepts_its_own_name_and_index_zero(latin_ttf: Path) -> None:
    assert load_font(latin_ttf, 0).face_index == 0
    assert load_font(latin_ttf, "Test Latin").face_index == 0


def test_single_face_file_rejects_other_name(latin_ttf: Path) -> None:
    with pytest.raises(ConfigError):
        load_font(latin_ttf, "Something Else")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FontLoadError, match="not found"):
        load_font(tmp_path / "nope.ttf")


def test_directory_rejected(tmp_path: Path) -> None:
    with pytest.raises(FontLoadError, match="not a file"):
        load_font(tmp_path)


def test_garbage_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"this is not a font at all" * 10)
    with pytest.raises(FontLoadError, match="could not read"):
        load_font(bad)


def test_variable_font_rejected(variable_ttf: Path) -> None:
    with pytest.raises(UnsupportedFontError) as exc:
        load_font(variable_ttf)
    assert "variable" in exc.value.message
    assert exc.value.hint and "instancer" in exc.value.hint


def test_variable_font_allowed_on_request(variable_ttf: Path) -> None:
    assert load_font(variable_ttf, allow_variable=True).is_variable


@pytest.mark.realfont
def test_real_fonts_load(averia: Path, iansui: Path) -> None:
    g = load_font(averia)
    i = load_font(iansui)
    assert (g.outline, i.outline) == ("glyf", "glyf")
    assert g.face is not None and g.face.family == "Averia Serif Libre"
    assert i.face is not None and i.face.family == "Iansui"
