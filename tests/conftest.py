"""Shared pytest fixtures: tiny test fonts built once per test session."""

from __future__ import annotations

from pathlib import Path

import pytest

from fontfactory import build_cjk_otf, build_latin_ttf, build_ttc, build_variable_ttf


@pytest.fixture(scope="session")
def font_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("fonts")


@pytest.fixture(scope="session")
def latin_ttf(font_dir: Path) -> Path:
    return build_latin_ttf(font_dir / "TestLatin.ttf")


@pytest.fixture(scope="session")
def cjk_otf(font_dir: Path) -> Path:
    return build_cjk_otf(font_dir / "TestCJK.otf")


@pytest.fixture(scope="session")
def cjk_ttc(font_dir: Path) -> Path:
    """Two CJK faces in one collection: index 0 'Test CJK SC', index 1 'Test CJK JP'."""
    sc = build_cjk_otf(font_dir / "TestCJK-SC.otf", family="Test CJK SC")
    jp = build_cjk_otf(font_dir / "TestCJK-JP.otf", family="Test CJK JP")
    return build_ttc(font_dir / "TestCJK.ttc", [sc, jp])


@pytest.fixture(scope="session")
def variable_ttf(font_dir: Path) -> Path:
    return build_variable_ttf(font_dir / "TestVariable.ttf")
