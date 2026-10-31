"""Bytes-in, bytes-out entry points for the browser (Pyodide) version.

The web page runs this module in a Web Worker. Fonts arrive as bytes, settings as a
dict shaped like the TOML config (without file paths), and results go back as plain
Python values that convert cleanly to JavaScript (dicts, lists, str, int, bytes).

Everything runs through the same ``pipeline.run`` as the command line, in a temporary
folder (Pyodide's in-memory file system in the browser).
"""

from __future__ import annotations

import re
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from fontmerge import __version__
from fontmerge.errors import ConfigError, FontMergeError
from fontmerge.inspector import check_profile, describe_fs_type, inspect_font
from fontmerge.loader import list_faces, load_font
from fontmerge.models import FontProfile, MergeConfig, Source
from fontmerge.pipeline import run
from fontmerge.writer import report_to_dict

Progress = Callable[[str], None]

OUTPUT_FORMATS = ("ttf", "otf", "woff2")
DEFAULT_FORMAT = "ttf"


def version() -> str:
    return __version__


def inspect_bytes(data: bytes, face: int | str | None = None, name: str = "font") -> dict[str, Any]:
    """Faces in a font file, and a profile of the selected (or only) face.

    For a collection with several faces and no face chosen, ``profile`` is ``None`` and
    the caller should ask the user to pick one of ``faces``.
    """
    with tempfile.TemporaryDirectory(prefix="fontmerge-") as tmp:
        path = Path(tmp) / _safe_name(name, "font.ttf")
        path.write_bytes(bytes(data))
        faces = list_faces(path)
        result: dict[str, Any] = {
            "faces": [
                {"index": f.index, "name": f.full_name or f.family, "family": f.family}
                for f in faces
            ],
            "profile": None,
        }
        if len(faces) > 1 and face is None:
            return result
        src = load_font(path, face, allow_variable=True)
        profile = inspect_font(src)
        result["profile"] = profile_to_dict(profile, src.is_variable)
        result["selected_face"] = src.face_index
        return result


def merge_bytes(
    western: bytes,
    cjk: bytes,
    settings: Mapping[str, Any] | None = None,
    progress: Progress | None = None,
    *,
    western_name: str = "western.ttf",
    cjk_name: str = "cjk.ttf",
) -> dict[str, Any]:
    """Merge two fonts given as bytes.

    ``settings`` uses the config file's shape, minus paths, e.g.::

        {"western_face": None, "cjk_face": 0,
         "naming": {"family": "Iansui Literata", "style": "Light"},
         "normalize": {"western_scale": 0.96}, "format": "ttf"}

    Returns ``{"filename", "format", "font" (bytes), "report", "seconds", "version"}``.
    Raises ``FontMergeError`` (with ``message`` and ``hint``) on any user-facing problem.
    """
    settings = dict(settings or {})
    fmt = str(settings.pop("format", DEFAULT_FORMAT)).lower()
    if fmt not in OUTPUT_FORMATS:
        raise ConfigError(f"unknown output format {fmt!r}", hint="use ttf, otf or woff2")
    western_face = settings.pop("western_face", None)
    cjk_face = settings.pop("cjk_face", None)
    naming = dict(settings.pop("naming", {}) or {})
    if not naming.get("family"):
        raise ConfigError("a family name is required", hint="enter a family name for the new font")

    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fontmerge-") as tmp:
        root = Path(tmp)
        w_path = root / ("w-" + _safe_name(western_name, "western.ttf"))
        c_path = root / ("c-" + _safe_name(cjk_name, "cjk.ttf"))
        w_path.write_bytes(bytes(western))
        c_path.write_bytes(bytes(cjk))
        filename = output_filename(naming["family"], naming.get("style") or "Regular", fmt)
        out_path = root / "out" / filename

        data: dict[str, Any] = {
            **settings,
            "western": {"path": w_path, "face": western_face},
            "cjk": {"path": c_path, "face": cjk_face},
            "output": {"path": out_path, "write_report": False},
            "naming": naming,
        }
        try:
            cfg = MergeConfig.model_validate(data)
        except ValidationError as e:
            raise ConfigError("invalid settings: " + _describe(e)) from e

        result = run(cfg, progress)
        font_bytes = result.outputs[0].read_bytes()

    return {
        "filename": filename,
        "format": fmt,
        "font": font_bytes,
        "report": report_to_dict(result.report),
        "seconds": round(time.monotonic() - start, 2),
        "version": __version__,
    }


def error_to_dict(error: BaseException) -> dict[str, Any]:
    """A user-facing error as a dict; unexpected errors keep their type name."""
    if isinstance(error, FontMergeError):
        return {"kind": type(error).__name__, "message": error.message, "hint": error.hint}
    return {"kind": type(error).__name__, "message": str(error), "hint": None}


def profile_to_dict(p: FontProfile, is_variable: bool = False) -> dict[str, Any]:
    cps = p.codepoints

    def count(lo: int, hi: int) -> int:
        return sum(1 for cp in cps if lo <= cp <= hi)

    def role(source: Source) -> list[dict[str, str]]:
        return [
            {"severity": i.severity.value, "code": i.code, "message": i.message}
            for i in check_profile(p, source)
        ]

    return {
        "family": p.family_name,
        "upm": p.upm,
        "glyphs": p.glyph_count,
        "characters": len(cps),
        "outline": p.outline,
        "variable": is_variable,
        "x_height": p.x_height,
        "cap_height": p.cap_height,
        "line_height_em": round(p.metrics.line_height / p.upm, 3),
        "vertical_metrics": p.has_vertical_metrics,
        "coverage": {
            "latin": count(0x20, 0x24F),
            "greek": count(0x370, 0x3FF),
            "cyrillic": count(0x400, 0x4FF),
            "han": count(0x4E00, 0x9FFF),
            "kana": count(0x3040, 0x30FF),
            "hangul": count(0xAC00, 0xD7AF),
        },
        "embedding": describe_fs_type(p.fs_type),
        "reserved_font_names": list(p.license.reserved_font_names),
        "license_url": p.license.license_url,
        "as_western": role(Source.WESTERN),
        "as_cjk": role(Source.CJK),
    }


def output_filename(family: str, style: str, fmt: str) -> str:
    def clean(s: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", s)

    stem = f"{clean(family) or 'Merged'}-{clean(style) or 'Regular'}"
    return f"{stem}.{fmt}"


# --------------------------------------------------------------------------------------


def _safe_name(name: str, default: str) -> str:
    base = Path(str(name)).name
    base = re.sub(r"[^\w.\-]", "_", base)[:100]
    return base or default


def _describe(error: ValidationError) -> str:
    parts = []
    for err in error.errors():
        where = ".".join(str(p) for p in err["loc"]) or "settings"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)
