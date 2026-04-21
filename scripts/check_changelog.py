#!/usr/bin/env python3
"""Pre-release invariant: the version in pyproject.toml must have a matching
`## <version>` header in CHANGELOG.md AND the previous version's header must
still be present.

This catches the class of bug where a release commit overwrites the previous
version's section header instead of prepending above it (see git history around
v0.3.2 → v0.3.3, where the 0.3.2 header was accidentally replaced by 0.3.3 and
the 0.3.2 body was left orphaned under a mis-labelled header).

Usage:
  python scripts/check_changelog.py

Exits 0 on success, non-zero with a clear message on violation. Intended to
run in CI on any PR that modifies pyproject.toml.
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

HEADER_RE = re.compile(r"^## (\d+\.\d+\.\d+)\b")


def read_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    v: str = data["project"]["version"]
    return v


def read_headers() -> list[str]:
    """Return the list of `## X.Y.Z` version strings in CHANGELOG.md, top-first."""
    out: list[str] = []
    for line in CHANGELOG.read_text().splitlines():
        m = HEADER_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def predecessor(version: str) -> str | None:
    """Return the immediately-previous semver we'd expect to see in CHANGELOG.
    Patch decrement only — minor and major transitions are rare enough that a
    human can override by passing `--no-predecessor-check` (not implemented;
    revisit when the first such transition happens)."""
    parts = version.split(".")
    if len(parts) != 3:
        return None
    major, minor, patch = parts
    try:
        patch_n = int(patch)
    except ValueError:
        return None
    if patch_n == 0:
        return None  # 0.X.0 — predecessor is 0.(X-1).?, don't guess
    return f"{major}.{minor}.{patch_n - 1}"


def main() -> int:
    version = read_version()
    headers = read_headers()

    # Invariant 1: exactly one header for the current version.
    count = headers.count(version)
    if count == 0:
        print(
            f"ERROR: pyproject.toml version is {version} but CHANGELOG.md "
            f"has no `## {version}` header.",
            file=sys.stderr,
        )
        return 1
    if count > 1:
        print(
            f"ERROR: CHANGELOG.md has {count} `## {version}` headers "
            f"(expected exactly 1).",
            file=sys.stderr,
        )
        return 1

    # Invariant 2: the predecessor version's header must still be present
    # (catches the header-overwrite class of bug).
    prev = predecessor(version)
    if prev is not None and prev not in headers:
        print(
            f"ERROR: CHANGELOG.md lost its `## {prev}` header. The current "
            f"release commit may have overwritten it instead of prepending. "
            f"Present version headers (top-first): {headers[:5]}",
            file=sys.stderr,
        )
        return 1

    # Invariant 3: the current version's header must be TOPMOST among version
    # headers (i.e., the newest section is on top).
    if headers[0] != version:
        print(
            f"ERROR: top-most `## <version>` header in CHANGELOG.md is "
            f"`{headers[0]}` but pyproject.toml version is `{version}`.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: CHANGELOG.md has `## {version}` on top; predecessor "
          f"`{prev}` still present." if prev else
          f"OK: CHANGELOG.md has `## {version}` on top.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
