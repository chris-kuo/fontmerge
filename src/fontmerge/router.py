"""Script Router: decide which source font supplies each codepoint.

Only codepoints at least one input font covers are routed. For each one:

1. **Overrides** from the config win, if the forced font has the character.
2. Otherwise the codepoint's **category** (from its Unicode block) gives a preferred
   font: Western scripts -> Western font, CJK -> CJK font, punctuation -> the
   punctuation policy, symbols -> the ``symbols`` setting, Hangul -> CJK font or left
   out, any other script -> Western font first.
3. If the preferred font lacks the character, it **falls back** to the other font
   (unless fallback is off, in which case the codepoint is reported missing).

Every assigned codepoint gets a ``RouteDecision`` naming the rule that chose it, so the
result can be explained character by character.
"""

from __future__ import annotations

from collections import Counter

from fontmerge.models import (
    AssignmentPlan,
    FontProfile,
    PunctuationPolicy,
    RouteDecision,
    RoutingConfig,
    Source,
)
from fontmerge.unicode_ranges import (
    CJK_PREFERRED_PUNCTUATION,
    Category,
    block_of,
    category_of,
)

FALLBACK_SUFFIX = ":fallback"


def build_plan(western: FontProfile, cjk: FontProfile, cfg: RoutingConfig) -> AssignmentPlan:
    coverage = {Source.WESTERN: western.codepoints, Source.CJK: cjk.codepoints}
    to_western: set[int] = set()
    to_cjk: set[int] = set()
    missing: set[int] = set()
    excluded: set[int] = set()
    decisions: list[RouteDecision] = []

    for cp in sorted(western.codepoints | cjk.codepoints):
        decision = _route(cp, coverage, cfg)
        if decision is None:
            excluded.add(cp)
            continue
        source, rule = decision
        if source is None:
            missing.add(cp)
            continue
        (to_western if source is Source.WESTERN else to_cjk).add(cp)
        decisions.append(RouteDecision(cp, source, rule))

    return AssignmentPlan(
        western=frozenset(to_western),
        cjk=frozenset(to_cjk),
        missing=frozenset(missing),
        excluded=frozenset(excluded),
        decisions=tuple(decisions),
    )


def summarize(plan: AssignmentPlan) -> dict[str, int]:
    """Count of assigned codepoints per rule, most common first."""
    return dict(Counter(d.rule for d in plan.decisions).most_common())


def fallbacks(plan: AssignmentPlan, source: Source | None = None) -> list[RouteDecision]:
    """Decisions where the preferred font lacked the character."""
    return [
        d
        for d in plan.decisions
        if d.rule.endswith(FALLBACK_SUFFIX) and (source is None or d.source is source)
    ]


# --------------------------------------------------------------------------------------


def _other(source: Source) -> Source:
    return Source.CJK if source is Source.WESTERN else Source.WESTERN


def _preferred(cp: int, cfg: RoutingConfig) -> tuple[Source, str] | None:
    """Preferred source and rule name for a codepoint; ``None`` = excluded."""
    category = category_of(cp)
    block = block_of(cp)
    where = block.name if block else f"U+{cp:04X}"

    if category is Category.WESTERN:
        return Source.WESTERN, f"western:{where}"
    if category is Category.CJK:
        return Source.CJK, f"cjk:{where}"
    if category is Category.HANGUL:
        if not cfg.include_hangul:
            return None
        return Source.CJK, f"hangul:{where}"
    if category is Category.SYMBOL:
        return cfg.symbols, f"symbol-{cfg.symbols.value}:{where}"
    if category is Category.PUNCTUATION:
        policy = cfg.punctuation
        if policy is PunctuationPolicy.CJK:
            return Source.CJK, "punctuation-cjk"
        if policy is PunctuationPolicy.WESTERN:
            return Source.WESTERN, "punctuation-western"
        if cp in CJK_PREFERRED_PUNCTUATION:
            return Source.CJK, "punctuation-split:cjk-specific"
        return Source.WESTERN, "punctuation-split"
    return Source.WESTERN, f"other:{where}"


def _route(
    cp: int, coverage: dict[Source, frozenset[int]], cfg: RoutingConfig
) -> tuple[Source | None, str] | None:
    """(source, rule) for a codepoint; source ``None`` = missing; ``None`` = excluded."""
    for override in reversed(cfg.overrides):
        if override.start <= cp <= override.end and cp in coverage[override.source]:
            return override.source, f"override:U+{override.start:04X}-U+{override.end:04X}"

    preferred = _preferred(cp, cfg)
    if preferred is None:
        return None
    source, rule = preferred
    if cp in coverage[source]:
        return source, rule
    if cfg.fallback and cp in coverage[_other(source)]:
        return _other(source), rule + FALLBACK_SUFFIX
    return None, rule
