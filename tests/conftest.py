"""Shared pytest fixtures: tiny test fonts built once per test session."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from fontfactory import build_cjk_otf, build_latin_ttf, build_ttc, build_variable_ttf

REAL_FONTS = Path(os.environ.get("FONTMERGE_REAL_FONTS", Path(__file__).parent / "realfonts"))


def _real_font(name: str) -> Path:
    path = REAL_FONTS / name
    if not path.exists():
        pytest.skip(f"real font {name} not found in {REAL_FONTS}")
    return path


@pytest.fixture(scope="session")
def literata() -> Path:
    """Western real font: Literata Light."""
    return _real_font("Literata-Light.ttf")


@pytest.fixture(scope="session")
def iansui() -> Path:
    """CJK real font: Iansui Regular (Traditional Chinese)."""
    return _real_font("Iansui-Regular.ttf")


@pytest.fixture(scope="session")
def real_merge(literata: Path, iansui: Path) -> dict[str, Any]:
    """Literata Light + Iansui through every stage so far (slow: built once per session).

    Settings are the target merge: Literata at 96%, Iansui's line height,
    named "Iansui Literata Light".
    """
    from fontmerge.inspector import inspect_font
    from fontmerge.loader import load_font
    from fontmerge.merge import merge_fonts
    from fontmerge.metadata import build_metadata
    from fontmerge.models import MetricsConfig, NamingConfig, NormalizeConfig, RoutingConfig
    from fontmerge.normalize import normalize, plan_normalization
    from fontmerge.router import build_plan
    from fontmerge.subset import subset_pair

    w_src, c_src = load_font(literata), load_font(iansui)
    w_prof, c_prof = inspect_font(w_src), inspect_font(c_src)
    route = build_plan(w_prof, c_prof, RoutingConfig())
    w, c = subset_pair(w_src, c_src, route)
    plan = plan_normalization(w_prof, c_prof, NormalizeConfig(western_scale=0.96))
    w, c = normalize(w, c, plan)
    merged = merge_fonts(w, c)
    naming = NamingConfig(family="Iansui Literata", style="Light")
    build_metadata(merged, w_prof, c_prof, naming, MetricsConfig(), plan)
    return {
        "font": merged,
        "western": w,
        "cjk": c,
        "route": route,
        "plan": plan,
        "w_prof": w_prof,
        "c_prof": c_prof,
    }


@pytest.fixture
def small_merge(latin_ttf: Path, cjk_otf: Path) -> dict[str, Any]:
    """The generated test fonts through every stage up to metadata (fast; fresh per test)."""
    from fontmerge.inspector import inspect_font
    from fontmerge.loader import load_font
    from fontmerge.merge import merge_fonts
    from fontmerge.metadata import build_metadata
    from fontmerge.models import NamingConfig, NormalizePlan, RoutingConfig
    from fontmerge.normalize import normalize
    from fontmerge.router import build_plan
    from fontmerge.subset import subset_pair

    w_src, c_src = load_font(latin_ttf), load_font(cjk_otf)
    w_prof, c_prof = inspect_font(w_src), inspect_font(c_src)
    route = build_plan(w_prof, c_prof, RoutingConfig())
    w, c = subset_pair(w_src, c_src, route)
    plan = NormalizePlan(
        target_upm=1000, target_outline="glyf", vertical_advance=1000, vertical_top=880
    )
    w, c = normalize(w, c, plan)
    merged = merge_fonts(w, c)
    build_metadata(merged, w_prof, c_prof, NamingConfig(family="Test Merged"), None, plan)
    return {"font": merged, "western": w, "cjk": c, "route": route}


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
