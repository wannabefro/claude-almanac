"""Curator provider protocol.

Each provider turns a (system_prompt, user_turn) pair into a raw model
response string. The orchestrator in ``core/curator.py`` parses the
returned string as JSON; on error the impl MUST return ``""`` or
``"{}"`` so ``_parse_decisions`` yields ``[]``. Providers never raise.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Curator(Protocol):
    name: str         # provider id: "ollama" | "anthropic_sdk"
    model: str        # "gemma3:4b", "claude-haiku-4-5-20251001", etc.
    timeout_s: float  # seconds; fractional values are permitted

    def invoke(self, system_prompt: str, user_turn: str) -> str: ...
