"""Wait until a deployed site serves the build for a given commit.

Usage:  python scripts/wait_for_deploy.py URL COMMIT [--timeout 600]

GitHub Pages can keep serving the previous version for a few minutes after a deploy;
this polls ``build.json`` so the live tests run against the new build, not the old one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request


def deployed_commit(url: str) -> str | None:
    request = urllib.request.Request(
        url.rstrip("/") + f"/build.json?t={time.time():.0f}",
        headers={"Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return str(json.load(response).get("commit"))
    except (OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument("commit")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    while True:
        found = deployed_commit(args.url)
        if found == args.commit:
            print(f"{args.url} serves {found}")
            return 0
        if time.monotonic() > deadline:
            print(f"::error::{args.url} still serves {found}, expected {args.commit}")
            return 1
        print(f"waiting: {args.url} serves {found}")
        time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
