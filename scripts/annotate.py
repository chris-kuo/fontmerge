"""Turn tool output into GitHub Actions annotations (readable through the API).

Usage:
  python scripts/annotate.py mypy LOG       # "file:line: error: msg" -> ::error
  python scripts/annotate.py pytest LOG     # FAILED/ERROR lines -> ::error
  python scripts/annotate.py benchmark JSON # -> ::notice with the numbers
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def esc(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main() -> int:
    kind, path = sys.argv[1], Path(sys.argv[2])
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    if kind == "mypy":
        for m in re.finditer(r"^(\S+?):(\d+): error: (.+)$", text, re.M):
            print(f"::error file={m[1]},line={m[2]},title=mypy::{esc(m[3])}")
    elif kind == "pytest":
        lines = [ln for ln in text.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
        for ln in lines[:20]:
            print(f"::error title=pytest::{esc(ln[:900])}")
        tail = [ln for ln in text.splitlines() if re.match(r"^=+ .*(passed|failed|error)", ln)]
        if tail:
            print(f"::notice title=pytest summary::{esc(tail[-1])}")
    elif kind == "benchmark":
        data = json.loads(text)
        print(f"::notice title=Browser benchmark::{esc(json.dumps(data))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
