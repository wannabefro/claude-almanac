"""Auto-inject gate: decides whether a user prompt warrants a code-index lookup.

The original heuristic is borrowed from memory-tools/code_autoinject.py and
counts signals (backticked tokens, camelCase, dotted/scoped names, file paths,
"how does X work" idioms). Prompts scoring >= SIGNAL_THRESHOLD open the gate.
"""
from __future__ import annotations

import re

_SIGNALS = [
    re.compile(r"`[^`]+`"),
    re.compile(r"\b[a-z]+[A-Z][a-zA-Z]+\b"),
    re.compile(r"[A-Z][a-zA-Z]+(?:\.|::)[a-zA-Z]+"),
    re.compile(r"\b[\w/]+\.(py|ts|tsx|js|jsx|go|tf|yaml|yml|rs|java)\b"),
    re.compile(r"how (does|do|is|are) `?\w+`? (work|used|called)", re.I),
    re.compile(r"where is `?\w+`? (used|defined|called)", re.I),
]

SIGNAL_THRESHOLD = 2


def signal_count(prompt: str) -> int:
    return sum(len(pat.findall(prompt)) for pat in _SIGNALS)


def should_query(prompt: str) -> bool:
    return signal_count(prompt) >= SIGNAL_THRESHOLD
