"""Dispatcher: picks the right extractor per file, falls back safely.

Fast paths handle known languages via AST (Python) or tuned regexes
(TS/JS/Go/Java). Exceptions from a fast path trigger a Serena fallback. An
empty result from a fast path is trusted — the language is supported and
the file legitimately has no extractable top-level symbols.
"""
from __future__ import annotations

from pathlib import Path

from .base import SymbolRef
from . import python_ast as _py
from . import regex_tuned as _rt
from . import serena_fallback as _sf


_FAST_PATHS = {
    "py":   _py,
    "ts":   _rt,
    "tsx":  _rt,
    "js":   _rt,
    "jsx":  _rt,
    "go":   _rt,
    "java": _rt,
}


def extract_symbols(abs_path: str, relative_path: str, repo_root: str) -> list[SymbolRef]:
    ext = Path(abs_path).suffix.lstrip(".").lower()
    fast_mod = _FAST_PATHS.get(ext)
    if fast_mod is not None:
        try:
            return fast_mod.extract(abs_path, relative_path)
        except Exception:
            pass
    try:
        return _sf.extract(abs_path, relative_path)
    except Exception:
        return []
