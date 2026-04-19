"""Serena-backed extractor for languages without a fast path (Rust, etc.).

Behavioral contract: **never raises**. Any error path returns [] so the
dispatcher can continue past an unreachable Serena daemon without aborting
the whole indexing pass.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import SymbolRef
from .. import serena_client


def extract(abs_path: str, relative_path: str) -> list[SymbolRef]:
    repo_root = _repo_root_from_paths(abs_path, relative_path)
    try:
        syms = serena_client.get_symbols_overview(repo_root, relative_path)
    except Exception:
        return []
    try:
        source = Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = source.splitlines()
    out: list[SymbolRef] = []
    for s in syms:
        line = _find_symbol_line(lines, s.name)
        if line is None:
            continue
        visibility = _visibility_for_language(abs_path, s.name, lines, line)
        signature = lines[line - 1][:400] if line - 1 < len(lines) else ""
        out.append(SymbolRef(
            name=s.name, kind=s.kind, visibility=visibility,
            line_start=line, line_end=s.line_end or line,
            signature=signature,
        ))
    return out


def _repo_root_from_paths(abs_path: str, relative_path: str) -> str:
    abs_p = Path(abs_path)
    rel_p = Path(relative_path)
    try:
        root = abs_p
        for _ in rel_p.parts:
            root = root.parent
        return str(root)
    except Exception:
        return str(abs_p.parent)


def _find_symbol_line(lines: list[str], name: str) -> int | None:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    for i, line in enumerate(lines, start=1):
        if pattern.search(line):
            return i
    return None


def _visibility_for_language(abs_path: str, name: str, lines: list[str], line: int) -> str:
    suffix = Path(abs_path).suffix.lower()
    if suffix == ".py":
        return "private" if name.startswith("_") else "public"
    if suffix == ".go":
        return "public" if (name and name[0].isupper()) else "private"
    if suffix in (".ts", ".tsx", ".js", ".jsx"):
        window_start = max(0, line - 2)
        window_end = min(len(lines), line + 5)
        window = "\n".join(lines[window_start:window_end])
        return "public" if re.search(r"\bexport\b", window) else "private"
    if suffix == ".java":
        idx = line - 1
        if 0 <= idx < len(lines):
            return "public" if re.search(r"\bpublic\b", lines[idx]) else "private"
        return "private"
    return "public"
