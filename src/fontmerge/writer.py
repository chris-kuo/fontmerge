"""Writer: save the merged font and its validation report.

Refuses to write when the report has errors (or warnings, in strict mode). Each file is
written to a temporary name first and then renamed, so a failed run never leaves a
half-written font behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont

from fontmerge.errors import ConfigError, ValidationFailedError
from fontmerge.models import OutputConfig, OutputFormat, Severity, ValidationReport
from fontmerge.validate import format_report


def woff2_available() -> bool:
    try:
        import brotli  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def output_paths(cfg: OutputConfig) -> dict[OutputFormat, Path]:
    base = cfg.path.with_suffix("")
    return {fmt: base.with_suffix(f".{fmt}") for fmt in cfg.resolved_formats()}


def report_path(cfg: OutputConfig) -> Path:
    return cfg.path.with_suffix("").with_suffix(".report.json")


def write_outputs(font: TTFont, report: ValidationReport, cfg: OutputConfig) -> list[Path]:
    """Write every requested format (and the report); return the paths written."""
    if report.blocks_output(cfg.strict):
        blockers = report.by_severity(Severity.ERROR) or report.by_severity(Severity.WARNING)
        raise ValidationFailedError(
            f"the merged font has {len(blockers)} blocking issue(s); first: "
            f"{blockers[0].code}: {blockers[0].message}",
            hint="see the report for details" + ("; or run without --strict" if cfg.strict else ""),
        )
    paths = output_paths(cfg)
    if "woff2" in paths and not woff2_available():
        raise ConfigError(
            "WOFF2 output needs the brotli package",
            hint="pip install brotli (or fontmerge[woff2])",
        )

    buf = BytesIO()
    font.save(buf)
    data = buf.getvalue()

    written: list[Path] = []
    for fmt, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "woff2":
            web = TTFont(BytesIO(data))
            web.flavor = "woff2"
            out = BytesIO()
            web.save(out)
            _atomic_write(path, out.getvalue())
        else:
            _atomic_write(path, data)
        written.append(path)

    if cfg.write_report:
        rp = report_path(cfg)
        _atomic_write(rp, json.dumps(report_to_dict(report), indent=2).encode())
        written.append(rp)
    return written


def report_to_dict(report: ValidationReport) -> dict[str, Any]:
    return {
        "glyph_count": report.glyph_count,
        "coverage": {s.value: n for s, n in report.coverage.items()},
        "has_errors": report.has_errors,
        "issues": [
            {
                "severity": i.severity.value,
                "code": i.code,
                "message": i.message,
                **({"codepoint": f"U+{i.codepoint:04X}"} if i.codepoint is not None else {}),
                **({"glyph": i.glyph} if i.glyph else {}),
            }
            for i in report.issues
        ],
        "summary": format_report(report),
    }


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # mkstemp creates owner-only files; give the result normal permissions.
        os.chmod(tmp, 0o666 & ~_umask())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
