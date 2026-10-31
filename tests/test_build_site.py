"""W1: the static site build (web files + a stdlib-built wheel)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
assert SPEC and SPEC.loader
build_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_site)


def test_site_layout(tmp_path: Path) -> None:
    out = build_site.build_site(tmp_path / "site")
    for name in ("index.html", "app.js", "worker.js", "i18n.js", "style.css", ".nojekyll"):
        assert (out / name).exists(), name
    build = json.loads((out / "build.json").read_text())
    assert build["version"] == "0.1.0"
    assert (out / build["wheel"]).exists()
    assert build["commit"]


def test_wheel_contents(tmp_path: Path) -> None:
    wheel = build_site.build_wheel(tmp_path)
    assert wheel.name == "fontmerge-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        assert "fontmerge/web.py" in names and "fontmerge/pipeline.py" in names
        assert "fontmerge-0.1.0.dist-info/METADATA" in names
        record = zf.read("fontmerge-0.1.0.dist-info/RECORD").decode()
        assert "fontmerge/web.py,sha256=" in record
        meta = zf.read("fontmerge-0.1.0.dist-info/METADATA").decode()
        assert "Requires-Dist: fonttools>=4.50" in meta


def test_wheel_is_importable(tmp_path: Path) -> None:
    wheel = build_site.build_wheel(tmp_path)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import fontmerge.web as w; "
        "assert w.__file__.startswith(sys.argv[1]); print(w.version())"
    )
    out = subprocess.run(
        [sys.executable, "-c", code, str(wheel)], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "0.1.0"


def test_wheel_is_reproducible(tmp_path: Path) -> None:
    a = build_site.build_wheel(tmp_path / "a").read_bytes()
    b = build_site.build_wheel(tmp_path / "b").read_bytes()
    assert a == b


def test_web_files_reference_each_other() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in html and 'href="style.css"' in html
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "./worker.js" in app and "./i18n.js" in app
    worker = (ROOT / "web" / "worker.js").read_text(encoding="utf-8")
    assert 'PYODIDE_VERSION = "314.0.5"' in worker


def test_every_ui_string_is_translated() -> None:
    import re

    text = (ROOT / "web" / "i18n.js").read_text(encoding="utf-8")
    en_block = text.split('"zh-Hant": {')[0]
    zh_block = text.split('"zh-Hant": {')[1].split("};")[0]
    key = re.compile(r"^\s{4}(\w+):", re.M)
    en_keys, zh_keys = set(key.findall(en_block)), set(key.findall(zh_block))
    assert en_keys == zh_keys, en_keys ^ zh_keys
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-placeholder|-title)?="(\w+)"', html))
    assert used <= en_keys, used - en_keys
