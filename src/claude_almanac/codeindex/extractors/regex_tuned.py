"""Regex-tuned symbol extractor for TypeScript, JavaScript, Go, and Java."""
from __future__ import annotations

import re
from pathlib import Path

from .base import SymbolRef

MAX_SCAN_LINES = 2000

_TS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("function", re.compile(r"^(?P<export>export\s+(?:default\s+)?)?(?:async\s+)?function\s+(?P<name>\w+)")),
    ("class",    re.compile(r"^(?P<export>export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(?P<name>\w+)")),
    ("interface",re.compile(r"^(?P<export>export\s+)?interface\s+(?P<name>\w+)")),
    ("type",     re.compile(r"^(?P<export>export\s+)?type\s+(?P<name>\w+)\s*=")),
    ("enum",     re.compile(r"^(?P<export>export\s+)?(?:const\s+)?enum\s+(?P<name>\w+)")),
    ("variable", re.compile(r"^(?P<export>export\s+(?:default\s+)?)?(?:const|let|var)\s+(?P<name>\w+)")),
]

_GO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("function", re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(?P<name>\w+)\s*\(")),
    ("type",     re.compile(r"^type\s+(?P<name>\w+)\s+(?:struct|interface|func|\w)")),
    ("variable", re.compile(r"^(?:var|const)\s+(?P<name>\w+)\b")),
]

_JAVA_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("class",    re.compile(r"^(?P<mods>(?:(?:public|private|protected|static|abstract|final|sealed)\s+)*)(?:class|interface|enum|record)\s+(?P<name>\w+)")),
    ("function", re.compile(r"^(?P<mods>(?:(?:public|private|protected|static|abstract|final|synchronized|native|default)\s+)+)(?:\w[\w<>\[\],\s]*?\s+)?(?P<name>\w+)\s*\(")),
]

_LANG_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "ts": _TS_PATTERNS, "tsx": _TS_PATTERNS, "js": _TS_PATTERNS, "jsx": _TS_PATTERNS,
    "go": _GO_PATTERNS, "java": _JAVA_PATTERNS,
}


def _ts_visibility(line: str) -> str:
    return "public" if re.search(r"\bexport\b", line) else "private"


def _go_visibility(name: str) -> str:
    return "public" if (name and name[0].isupper()) else "private"


def _java_visibility(line: str) -> str:
    return "public" if re.search(r"\bpublic\b", line) else "private"


def _find_line_end(lines: list[str], line_start: int) -> int:
    depth = 0
    idx_start = line_start - 1
    limit = min(len(lines), idx_start + MAX_SCAN_LINES)
    for i in range(idx_start, limit):
        depth += lines[i].count("{") - lines[i].count("}")
        if i > idx_start and depth <= 0:
            return i + 1
    return line_start


def extract(abs_path: str, relative_path: str) -> list[SymbolRef]:
    ext = Path(abs_path).suffix.lstrip(".").lower()
    patterns = _LANG_PATTERNS.get(ext)
    if patterns is None:
        return []
    try:
        raw = Path(abs_path).read_bytes()
        if b"\x00" in raw[:512]:
            return []
        source = raw.decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = source.splitlines()
    out: list[SymbolRef] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        for kind, pat in patterns:
            m = pat.match(stripped)
            if m is None:
                continue
            name = m.group("name")
            if not name or name in seen:
                continue
            seen.add(name)
            if ext in ("ts", "tsx", "js", "jsx"):
                visibility = _ts_visibility(stripped)
            elif ext == "go":
                visibility = _go_visibility(name)
            else:
                visibility = _java_visibility(stripped)
            line_end = _find_line_end(lines, lineno)
            signature = stripped[:400]
            out.append(SymbolRef(
                name=name, kind=kind, visibility=visibility,
                line_start=lineno, line_end=line_end, signature=signature,
            ))
            break
    return out
