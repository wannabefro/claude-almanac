"""Python symbol extractor using the stdlib ast module.

Zero external deps. Processes a 1000-line file in ~2ms.

Visibility rules (priority order):
  1. If __all__ is defined and the symbol is in it → 'public'
  2. If __all__ is defined and the symbol is NOT in it → 'private'
  3. If name starts with underscore → 'private'
  4. Otherwise → 'public'
"""
from __future__ import annotations

import ast
from pathlib import Path

from .base import SymbolRef


def extract(abs_path: str, relative_path: str) -> list[SymbolRef]:
    try:
        source = Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=relative_path)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    explicit_all = _extract_dunder_all(tree)
    out: list[SymbolRef] = []
    for node in tree.body:
        ref = _node_to_ref(node, lines, explicit_all)
        if ref is not None:
            out.append(ref)
    return out


def _extract_dunder_all(tree: ast.Module) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        names: set[str] = set()
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.add(elt.value)
                        return names
    return None


def _node_to_ref(node: ast.stmt, lines: list[str], explicit_all: set[str] | None) -> SymbolRef | None:
    name: str | None = None
    kind: str | None = None
    if isinstance(node, ast.FunctionDef):
        name, kind = node.name, "function"
    elif isinstance(node, ast.AsyncFunctionDef):
        name, kind = node.name, "function"
    elif isinstance(node, ast.ClassDef):
        name, kind = node.name, "class"
    elif isinstance(node, ast.Assign):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            if target_name.isupper() or target_name.startswith("_"):
                name, kind = target_name, "variable"
    if name is None or kind is None:
        return None
    visibility = _visibility(name, explicit_all)
    line_start = node.lineno
    line_end = getattr(node, "end_lineno", node.lineno) or line_start
    signature = _signature_from_lines(lines, line_start)
    return SymbolRef(name=name, kind=kind, visibility=visibility,
                     line_start=line_start, line_end=line_end, signature=signature)


def _visibility(name: str, explicit_all: set[str] | None) -> str:
    if explicit_all is not None:
        return "public" if name in explicit_all else "private"
    return "private" if name.startswith("_") else "public"


def _signature_from_lines(lines: list[str], line_start: int) -> str:
    if line_start < 1 or line_start > len(lines):
        return ""
    idx = line_start - 1
    first = lines[idx].rstrip()
    joined = first
    for off in range(1, 6):
        if idx + off >= len(lines):
            break
        if joined.rstrip().endswith((":", "{", ";")):
            break
        joined = joined + " " + lines[idx + off].strip()
    return joined[:400]
