"""Shared types for symbol extractors.

Each extractor returns a list of SymbolRef. Downstream code treats them
identically regardless of which extractor produced them. Add a new language by
implementing a function matching the Extractor protocol and registering it in
dispatch.py.
"""
from __future__ import annotations

import dataclasses as _dc
from typing import Protocol


@_dc.dataclass(frozen=True)
class SymbolRef:
    name: str
    kind: str                 # 'function' | 'class' | 'method' | 'variable' | 'type' | 'interface' | 'enum'
    visibility: str           # 'public' | 'private'
    line_start: int           # 1-based, inclusive
    line_end: int             # 1-based, inclusive
    signature: str            # one line (or joined multi-line), truncated at 400 chars


class Extractor(Protocol):
    def __call__(self, abs_path: str, relative_path: str) -> list[SymbolRef]: ...
