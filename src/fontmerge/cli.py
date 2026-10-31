"""Command line: ``fontmerge merge`` and ``fontmerge inspect``.

``fontmerge --western ...`` without a command means ``merge``. Exit codes: 0 success,
1 a fontmerge error (message and hint printed), 2 bad command-line usage.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fontmerge import __version__
from fontmerge.config import load_config, parse_face, parse_override
from fontmerge.errors import FontMergeError
from fontmerge.inspector import check_profile, describe_fs_type, inspect_font
from fontmerge.loader import list_faces, load_font
from fontmerge.models import Source
from fontmerge.pipeline import run
from fontmerge.validate import format_report

COMMANDS = ("merge", "inspect")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fontmerge",
        description="Merge a Western font and a CJK font into one font file.",
    )
    parser.add_argument("--version", action="version", version=f"fontmerge {__version__}")
    sub = parser.add_subparsers(dest="command")

    m = sub.add_parser(
        "merge",
        help="merge two fonts (the default command)",
        description="Merge a Western font and a CJK font. Command-line options override "
        "the config file.",
    )
    m.add_argument("-c", "--config", type=Path, help="TOML config file")

    g = m.add_argument_group("input fonts")
    g.add_argument("--western", type=Path, help="font for Latin and other Western scripts")
    g.add_argument("--western-face", help="face index or name, for a .ttc collection")
    g.add_argument("--cjk", type=Path, help="font for Chinese and Japanese")
    g.add_argument("--cjk-face", help="face index or name, for a .ttc collection")

    g = m.add_argument_group("output")
    g.add_argument("-o", "--output", type=Path, help="output font (.ttf, .otf or .woff2)")
    g.add_argument(
        "--format",
        action="append",
        choices=("ttf", "otf", "woff2"),
        help="also write this format (repeatable)",
    )
    g.add_argument("--preview", choices=("html", "png"), help="also write a preview sheet")
    g.add_argument("--no-report", action="store_true", help="do not write the JSON report")
    g.add_argument("--strict", action="store_true", help="treat warnings as errors")

    g = m.add_argument_group("naming")
    g.add_argument("--family", help='family name, e.g. "Iansui Literata"')
    g.add_argument("--style", help='style name, e.g. "Light" (default "Regular")')
    g.add_argument("--font-version", dest="font_version", help='e.g. "1.000"')
    g.add_argument("--vendor", help="4-character vendor ID")

    g = m.add_argument_group("routing")
    g.add_argument(
        "--punctuation",
        choices=("split", "western", "cjk"),
        help="which font supplies shared punctuation (default split)",
    )
    g.add_argument("--symbols", choices=("cjk", "western"), help="font for arrows, boxes, shapes")
    g.add_argument("--include-hangul", action="store_true", default=None, help="keep Korean")
    g.add_argument(
        "--no-fallback",
        action="store_true",
        help="leave out characters the preferred font lacks",
    )
    g.add_argument(
        "--override",
        action="append",
        metavar="RANGE=FONT",
        help='force a range to a font, e.g. "U+2018-U+201D=cjk" (repeatable)',
    )

    g = m.add_argument_group("sizing and metrics")
    g.add_argument("--scale", type=float, help="scale for Western glyphs (default: automatic)")
    g.add_argument("--baseline-shift", type=int, help="move Western glyphs up (+) or down (-)")
    g.add_argument("--outline", choices=("auto", "glyf", "CFF"), help="output outline format")
    g.add_argument(
        "--line-height",
        choices=("cjk", "western", "max"),
        help="whose line spacing to use (default cjk)",
    )
    m.add_argument("-q", "--quiet", action="store_true", help="print only errors")

    i = sub.add_parser("inspect", help="show what fontmerge sees in a font")
    i.add_argument("font", type=Path)
    i.add_argument("--face", help="face index or name, for a .ttc collection")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    first = args_list[0] if args_list else ""
    if first.startswith("-") and first not in ("-h", "--help", "--version"):
        args_list.insert(0, "merge")
    parser = build_parser()
    args = parser.parse_args(args_list)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        if args.command == "inspect":
            return _inspect(args)
        return _merge(args)
    except FontMergeError as e:
        print(f"error: {e.message}", file=sys.stderr)
        if e.hint:
            print(f"  hint: {e.hint}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------------------


def cli_values(args: argparse.Namespace) -> dict[str, Any]:
    """Command-line options as a nested dict shaped like the config file."""
    overrides = [parse_override(o) for o in args.override] if args.override else None
    return {
        "western": {"path": args.western, "face": parse_face(args.western_face)},
        "cjk": {"path": args.cjk, "face": parse_face(args.cjk_face)},
        "output": {
            "path": args.output,
            "formats": tuple(args.format) if args.format else None,
            "preview": args.preview,
            "write_report": False if args.no_report else None,
            "strict": True if args.strict else None,
        },
        "naming": {
            "family": args.family,
            "style": args.style,
            "version": args.font_version,
            "vendor_id": args.vendor,
        },
        "routing": {
            "punctuation": args.punctuation,
            "symbols": args.symbols,
            "include_hangul": args.include_hangul,
            "fallback": False if args.no_fallback else None,
            "overrides": overrides,
        },
        "normalize": {
            "western_scale": args.scale,
            "western_baseline_shift": args.baseline_shift,
            "target_outline": args.outline,
        },
        "metrics": {"line_height": args.line_height},
    }


def _merge(args: argparse.Namespace) -> int:
    cfg = load_config(cli_values(args), args.config)
    progress = None if args.quiet else (lambda msg: print(msg, file=sys.stderr))
    result = run(cfg, progress)
    if not args.quiet:
        print(format_report(result.report))
        print("Wrote:")
        for path in (*result.outputs, *((result.preview,) if result.preview else ())):
            print(f"  {path}")
    return 0


def _inspect(args: argparse.Namespace) -> int:
    faces = list_faces(args.font)
    if len(faces) > 1:
        print(f"{args.font.name}: {len(faces)} faces")
        for f in faces:
            print(f"  {f.index}: {f.full_name or f.family}")
        if args.face is None:
            return 0
    src = load_font(args.font, parse_face(args.face), allow_variable=True, option_name="--face")
    p = inspect_font(src)
    m = p.metrics
    cps = p.codepoints

    def count(lo: int, hi: int) -> int:
        return sum(1 for cp in cps if lo <= cp <= hi)

    lines = [
        f"{p.family_name} ({args.font.name}, face {src.face_index})",
        f"  outlines: {p.outline}{', variable' if src.is_variable else ''}",
        f"  units per em: {p.upm}   glyphs: {p.glyph_count:,}   characters: {len(cps):,}",
        f"  Latin {count(0x20, 0x24F)}, Greek {count(0x370, 0x3FF)}, "
        f"Cyrillic {count(0x400, 0x4FF)}, Han {count(0x4E00, 0x9FFF)}, "
        f"kana {count(0x3040, 0x30FF)}, Hangul {count(0xAC00, 0xD7AF)}",
        f"  x-height: {p.x_height}   cap height: {p.cap_height}",
        f"  line metrics (hhea): {m.hhea_ascender} / {m.hhea_descender} / {m.hhea_line_gap}"
        f"   line height: {m.line_height / p.upm:.2f} em",
        f"  ideographic em box: {p.ideo_embox}   vertical metrics: "
        f"{'yes' if p.has_vertical_metrics else 'no'}",
        f"  scripts: {', '.join(sorted(p.scripts)) or 'none'}",
        f"  features: {', '.join(sorted(p.features)) or 'none'}",
        f"  embedding: {describe_fs_type(p.fs_type)}",
        f"  reserved font names: {', '.join(p.license.reserved_font_names) or 'none'}",
    ]
    print("\n".join(lines))
    for role in (Source.WESTERN, Source.CJK):
        issues = check_profile(p, role)
        verdict = "ok" if not any(i.severity.value != "info" for i in issues) else "issues"
        print(f"  as the {role.value} font: {verdict}")
        for issue in issues:
            if issue.code != "license-reserved-names":
                print(f"    [{issue.severity.value}] {issue.message}")
    return 0
