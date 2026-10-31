"""Stage 2: Script Router."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

import pytest

from fontmerge.inspector import inspect_font
from fontmerge.loader import load_font
from fontmerge.models import (
    AssignmentPlan,
    FontProfile,
    LicenseInfo,
    PunctuationPolicy,
    RangeOverride,
    RoutingConfig,
    Source,
    VerticalMetrics,
)
from fontmerge.router import build_plan, fallbacks, summarize
from fontmerge.unicode_ranges import BLOCKS, Category, block_of, category_of

W, C = Source.WESTERN, Source.CJK


def profile(codepoints: Iterable[int], name: str = "Synthetic") -> FontProfile:
    """A FontProfile with only coverage filled in meaningfully."""
    return FontProfile(
        family_name=name,
        upm=1000,
        glyph_count=0,
        codepoints=frozenset(codepoints),
        outline="glyf",
        metrics=VerticalMetrics(800, -200, 0, 800, -200, 0, 1000, 300, False),
        x_height=None,
        cap_height=None,
        ideo_embox=None,
        ideo_char_face=None,
        has_vertical_metrics=False,
        features=frozenset(),
        scripts=frozenset(),
        fs_type=0,
        license=LicenseInfo(None, None, None),
    )


def plan_for(western: Iterable[int], cjk: Iterable[int], **cfg: object) -> AssignmentPlan:
    return build_plan(profile(western), profile(cjk), RoutingConfig.model_validate(cfg))


# Unicode block table --------------------------------------------------------------------


def test_blocks_sorted_and_disjoint() -> None:
    for a, b in pairwise(BLOCKS):
        assert a.start <= a.end < b.start, (a.name, b.name)


@pytest.mark.parametrize(
    ("cp", "category"),
    [
        (0x41, Category.WESTERN),
        (0x3B1, Category.WESTERN),
        (0x4E00, Category.CJK),
        (0x3042, Category.CJK),
        (0xFF21, Category.CJK),
        (0xAC00, Category.HANGUL),
        (0x2014, Category.PUNCTUATION),
        (0xB7, Category.PUNCTUATION),
        (0x2500, Category.SYMBOL),
        (0x0E01, Category.OTHER),  # Thai is not in the table
        (0x10FFFF, Category.OTHER),
    ],
)
def test_category_of(cp: int, category: Category) -> None:
    assert category_of(cp) is category


def test_block_of_edges() -> None:
    block = block_of(0x4E00)
    assert block is not None and block.name == "CJK Unified Ideographs"
    assert block_of(0x9FFF) is block
    assert block_of(0x0E01) is None


# Golden routing: both fonts cover everything, so only the rules decide ------------------

GOLDEN: list[tuple[int, Source, str]] = [
    (0x0020, W, "space"),
    (0x0041, W, "A"),
    (0x00E9, W, "é"),
    (0x00A0, W, "no-break space"),
    (0x0101, W, "ā (pinyin)"),
    (0x03B1, W, "Greek alpha"),
    (0x0416, W, "Cyrillic Zhe"),
    (0x20AC, W, "euro"),
    (0x2122, W, "trade mark"),
    (0x2212, W, "minus"),
    (0x00B7, W, "middle dot (split policy)"),
    (0x2014, W, "em dash (split policy)"),
    (0x201C, W, "left double quote (split policy)"),
    (0x2026, W, "ellipsis (split policy)"),
    (0x2025, C, "two dot leader (CJK-specific)"),
    (0x203B, C, "reference mark (CJK-specific)"),
    (0x2500, C, "box drawing (symbols=cjk)"),
    (0x2192, C, "rightwards arrow (symbols=cjk)"),
    (0x2460, C, "circled 1 (symbols=cjk)"),
    (0x25CB, C, "white circle (symbols=cjk)"),
    (0x3000, C, "ideographic space"),
    (0x3001, C, "ideographic comma"),
    (0x300C, C, "corner bracket"),
    (0x3042, C, "hiragana a"),
    (0x30A2, C, "katakana a"),
    (0x3105, C, "bopomofo b"),
    (0x31C0, C, "CJK stroke"),
    (0x3400, C, "Ext A"),
    (0x4E00, C, "一"),
    (0x9FA5, C, "URO"),
    (0xF900, C, "compatibility ideograph"),
    (0xFE10, C, "vertical comma"),
    (0xFF01, C, "full-width !"),
    (0xFF21, C, "full-width A"),
    (0xFF71, C, "half-width katakana"),
    (0x1B001, C, "kana supplement"),
    (0x20000, C, "Ext B"),
    (0x0E01, W, "Thai (other: Western first)"),
]


@pytest.mark.parametrize(("cp", "expected", "label"), GOLDEN, ids=[g[2] for g in GOLDEN])
def test_golden_routing(cp: int, expected: Source, label: str) -> None:
    everything = [g[0] for g in GOLDEN]
    plan = plan_for(everything, everything)
    assert plan.source_of(cp) is expected, label


def test_every_covered_codepoint_is_accounted_for() -> None:
    western = set(range(0x20, 0x250)) | {0x2014, 0xAC00}
    cjk = set(range(0x4E00, 0x4F00)) | {0x41, 0x2014, 0xAC00, 0x3001}
    plan = plan_for(western, cjk)
    accounted = plan.western | plan.cjk | plan.missing | plan.excluded
    assert accounted == western | cjk
    assert len(plan.decisions) == len(plan.western | plan.cjk)


def test_shared_latin_comes_from_western() -> None:
    plan = plan_for({0x41}, {0x41, 0x4E00})
    assert plan.source_of(0x41) is W
    d = plan.decision_for(0x41)
    assert d is not None and d.rule == "western:Basic Latin"


# Configurable rules ---------------------------------------------------------------------

PUNCT = [0x00B7, 0x2014, 0x201C, 0x2026, 0x2025]


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (PunctuationPolicy.SPLIT, [W, W, W, W, C]),
        (PunctuationPolicy.WESTERN, [W, W, W, W, W]),
        (PunctuationPolicy.CJK, [C, C, C, C, C]),
    ],
)
def test_punctuation_policy(policy: PunctuationPolicy, expected: list[Source]) -> None:
    plan = plan_for(PUNCT, PUNCT, punctuation=policy)
    assert [plan.source_of(cp) for cp in PUNCT] == expected


def test_symbols_setting() -> None:
    syms = [0x2500, 0x2192, 0x25A0]
    assert all(plan_for(syms, syms).source_of(cp) is C for cp in syms)
    assert all(plan_for(syms, syms, symbols="western").source_of(cp) is W for cp in syms)


def test_hangul_excluded_by_default() -> None:
    plan = plan_for({0x41}, {0xAC00, 0x1100, 0x3131})
    assert plan.excluded == {0xAC00, 0x1100, 0x3131}
    assert plan.source_of(0xAC00) is None


def test_hangul_included_on_request() -> None:
    plan = plan_for({0x41}, {0xAC00}, include_hangul=True)
    assert plan.source_of(0xAC00) is C
    assert not plan.excluded


# Fallback -------------------------------------------------------------------------------


def test_fallback_to_cjk_for_missing_western_character() -> None:
    plan = plan_for({0x41}, {0x41, 0x3B1, 0x101})  # CJK font has Greek alpha and ā
    assert plan.source_of(0x3B1) is C
    assert plan.source_of(0x101) is C
    assert {d.codepoint for d in fallbacks(plan, C)} == {0x3B1, 0x101}
    d = plan.decision_for(0x3B1)
    assert d is not None and d.rule == "western:Greek and Coptic:fallback"


def test_fallback_to_western_for_missing_cjk_character() -> None:
    plan = plan_for({0x2500}, {0x4E00})  # box drawing prefers CJK, only Western has it
    assert plan.source_of(0x2500) is W
    assert [d.codepoint for d in fallbacks(plan, W)] == [0x2500]


def test_fallback_off_reports_missing() -> None:
    plan = plan_for({0x41}, {0x41, 0x3B1}, fallback=False)
    assert plan.missing == {0x3B1}
    assert plan.source_of(0x3B1) is None


# Overrides ------------------------------------------------------------------------------


def test_override_forces_source() -> None:
    quotes = {0x2018, 0x2019, 0x201C, 0x201D}
    plan = plan_for(
        quotes | {0x41},
        quotes | {0x4E00},
        overrides=[{"start": 0x2018, "end": 0x201D, "source": "cjk"}],
    )
    assert all(plan.source_of(cp) is C for cp in quotes)
    d = plan.decision_for(0x201C)
    assert d is not None and d.rule == "override:U+2018-U+201D"


def test_later_override_wins() -> None:
    plan = plan_for(
        {0x2014},
        {0x2014},
        overrides=[
            RangeOverride(start=0x2000, end=0x206F, source=C),
            RangeOverride(start=0x2014, end=0x2014, source=W),
        ],
    )
    assert plan.source_of(0x2014) is W


def test_override_to_font_lacking_character_uses_normal_rules() -> None:
    plan = plan_for({0x41}, {0x4E00}, overrides=[{"start": 0x41, "end": 0x41, "source": "cjk"}])
    assert plan.source_of(0x41) is W
    d = plan.decision_for(0x41)
    assert d is not None and d.rule == "western:Basic Latin"


def test_summarize_counts_rules() -> None:
    plan = plan_for({0x41, 0x42}, {0x4E00, 0x3B1})
    counts = summarize(plan)
    assert counts["western:Basic Latin"] == 2
    assert counts["cjk:CJK Unified Ideographs"] == 1
    assert counts["western:Greek and Coptic:fallback"] == 1


# Real fonts -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_plan(averia: Path, iansui: Path) -> tuple[FontProfile, FontProfile, AssignmentPlan]:
    w = inspect_font(load_font(averia))
    c = inspect_font(load_font(iansui))
    return w, c, build_plan(w, c, RoutingConfig())


@pytest.mark.realfont
def test_real_every_averia_character_comes_from_averia(
    real_plan: tuple[FontProfile, FontProfile, AssignmentPlan],
) -> None:
    w, _, plan = real_plan
    assert w.codepoints <= plan.western
    assert plan.western == w.codepoints  # nothing falls back to Averia


@pytest.mark.realfont
def test_real_cjk_from_iansui(
    real_plan: tuple[FontProfile, FontProfile, AssignmentPlan],
) -> None:
    _, c, plan = real_plan
    han = {cp for cp in c.codepoints if 0x4E00 <= cp <= 0x9FFF}
    assert han <= plan.cjk
    for cp in (0x3001, 0x3002, 0x300C, 0x3042, 0x30A2, 0x3105, 0xFF0C):
        assert plan.source_of(cp) is C, f"U+{cp:04X}"
    assert not plan.missing and not plan.excluded  # Iansui has no Hangul


@pytest.mark.realfont
def test_real_western_gaps_fall_back_to_iansui(
    real_plan: tuple[FontProfile, FontProfile, AssignmentPlan],
) -> None:
    _, _, plan = real_plan
    fb = {d.codepoint for d in fallbacks(plan, C)}
    assert 0x03B1 in fb  # Greek: Averia has none
    assert 0x0430 in fb  # Cyrillic
    assert 0x0101 in fb  # ā: pinyin tone mark not in Averia
    assert 0x00E1 not in fb and plan.source_of(0x00E1) is W  # á is in Latin-1
