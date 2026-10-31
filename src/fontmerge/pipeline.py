"""Orchestrator: run every stage in order for one ``MergeConfig``.

Load -> inspect -> route -> subset -> normalize -> merge -> metadata -> validate ->
write (-> preview). Problems the Inspector finds (licence, role coverage) are carried
into the final report. An error-level problem stops the run with a
``FontMergeError``; when that happens after validation, the report is still written so
the user can read why.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from fontmerge.errors import UnsupportedFontError, ValidationFailedError
from fontmerge.inspector import check_profile, inspect_font
from fontmerge.loader import load_font
from fontmerge.merge import merge_fonts
from fontmerge.metadata import build_metadata
from fontmerge.models import (
    Issue,
    MergeConfig,
    MergeResult,
    Severity,
    Source,
    ValidationReport,
)
from fontmerge.normalize import normalize, plan_normalization
from fontmerge.preview import render_preview
from fontmerge.router import build_plan
from fontmerge.subset import subset_pair
from fontmerge.validate import validate
from fontmerge.writer import write_outputs, write_report

Progress = Callable[[str], None]


def run(cfg: MergeConfig, progress: Progress | None = None) -> MergeResult:
    say = _timed(progress)

    say("Loading fonts")
    w_src = load_font(cfg.western.path, cfg.western.face, option_name="--western-face")
    c_src = load_font(cfg.cjk.path, cfg.cjk.face, option_name="--cjk-face")

    say("Inspecting fonts")
    w_prof, c_prof = inspect_font(w_src), inspect_font(c_src)
    pre_issues = _role_issues(check_profile(w_prof, Source.WESTERN), "Western font")
    pre_issues += _role_issues(check_profile(c_prof, Source.CJK), "CJK font")
    blockers = [i for i in pre_issues if i.severity is Severity.ERROR]
    if blockers:
        raise UnsupportedFontError(blockers[0].message)

    say("Routing characters")
    route = build_plan(w_prof, c_prof, cfg.routing)
    if route.missing:
        pre_issues.append(
            Issue(
                Severity.WARNING,
                "not-routed",
                f"{len(route.missing)} characters were left out because fallback is off",
                codepoint=min(route.missing),
            )
        )

    say(f"Subsetting ({len(route.western):,} Western + {len(route.cjk):,} CJK characters)")
    western, cjk = subset_pair(w_src, c_src, route)

    plan = plan_normalization(w_prof, c_prof, cfg.normalize)
    say(f"Normalizing (UPM {plan.target_upm}, {plan.target_outline}, scale {plan.western_scale})")
    western, cjk = normalize(western, cjk, plan)

    say("Merging")
    font = merge_fonts(western, cjk)

    say("Writing names and metrics")
    build_metadata(font, w_prof, c_prof, cfg.naming, cfg.metrics, plan)

    say("Validating")
    checked = validate(font, route, (western, cjk))
    report = ValidationReport(
        issues=_sorted(pre_issues + list(checked.issues)),
        glyph_count=checked.glyph_count,
        coverage=checked.coverage,
    )

    if report.blocks_output(cfg.output.strict):
        hint = "run without --strict to write it anyway" if cfg.output.strict else None
        if cfg.output.write_report:
            rp = write_report(report, cfg.output)
            hint = f"details in {rp}" + (f"; {hint}" if hint else "")
        stoppers = report.by_severity(Severity.ERROR) or report.by_severity(Severity.WARNING)
        raise ValidationFailedError(
            f"no font written: {stoppers[0].code}: {stoppers[0].message}", hint=hint
        )

    say("Writing files")
    outputs = write_outputs(font, report, cfg.output)

    preview_path = None
    if cfg.output.preview:
        say("Rendering preview")
        target = cfg.output.path.with_suffix("").with_suffix(f".preview.{cfg.output.preview}")
        preview_path = render_preview(outputs[0], target)

    say("Done")
    return MergeResult(outputs=tuple(outputs), report=report, preview=preview_path)


# --------------------------------------------------------------------------------------


def _role_issues(issues: list[Issue], role: str) -> list[Issue]:
    return [Issue(i.severity, i.code, f"{role}: {i.message}", i.codepoint, i.glyph) for i in issues]


def _sorted(issues: list[Issue]) -> tuple[Issue, ...]:
    rank = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return tuple(sorted(issues, key=lambda i: rank[i.severity]))


def _timed(progress: Progress | None) -> Progress:
    """Wrap ``progress`` so each message also reports seconds since the start."""
    start = time.monotonic()

    def say(message: str) -> None:
        if progress is not None:
            progress(f"[{time.monotonic() - start:5.1f}s] {message}")

    return say
