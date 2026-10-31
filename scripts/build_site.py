"""Assemble the static web app: web/ + a fontmerge wheel + build.json.

Usage:  python scripts/build_site.py [--out _site]

The wheel is built with the standard library only (fontmerge is pure Python), so this
works without network access or build tools. Serve the result with any static server,
e.g. ``python -m http.server -d _site``; module workers do not run from file:// URLs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "fontmerge"
WEB = ROOT / "web"

sys.path.insert(0, str(ROOT / "src"))
from fontmerge import __version__  # noqa: E402

REQUIRES = ("fonttools>=4.50", "pydantic>=2.5")


def build_wheel(out_dir: Path, version: str = __version__) -> Path:
    """Write ``fontmerge-<version>-py3-none-any.whl`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"fontmerge-{version}-py3-none-any.whl"
    dist_info = f"fontmerge-{version}.dist-info"
    files: dict[str, bytes] = {}
    for path in sorted(SRC.rglob("*.py")):
        files[f"fontmerge/{path.relative_to(SRC).as_posix()}"] = path.read_bytes()
    metadata = [
        "Metadata-Version: 2.1",
        "Name: fontmerge",
        f"Version: {version}",
        "Summary: Merge a Western font and a CJK font into one font file",
        "License: MIT",
        "Requires-Python: >=3.11",
        *(f"Requires-Dist: {r}" for r in REQUIRES),
    ]
    files[f"{dist_info}/METADATA"] = ("\n".join(metadata) + "\n").encode()
    files[f"{dist_info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: fontmerge-build-site\nRoot-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    files[f"{dist_info}/licenses/LICENSE"] = (ROOT / "LICENSE").read_bytes()

    record_lines = []
    for arcname, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record_lines.append(f"{arcname},sha256={digest},{len(data)}")
    record_lines.append(f"{dist_info}/RECORD,,")
    files[f"{dist_info}/RECORD"] = ("\n".join(record_lines) + "\n").encode()

    wheel = out_dir / name
    fixed_time = (2020, 1, 1, 0, 0, 0)  # reproducible archives
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files.items():
            info = zipfile.ZipInfo(arcname, fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
    return wheel


def git_commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "dev"


def build_site(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB, out)
    wheel = build_wheel(out / "wheels")
    build = {
        "version": __version__,
        "commit": git_commit(),
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wheel": f"wheels/{wheel.name}",
    }
    (out / "build.json").write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # serve files as they are on Pages
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    out = build_site(args.out)
    print(f"Built {out} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file()):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
