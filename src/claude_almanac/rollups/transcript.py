"""Transcript JSONL reader + token-aware windowing for rollup input.

Claude Code writes one JSON object per line to
~/.claude/projects/<encoded-cwd>/<session-id>.jsonl. This module loads those
files, filters/shims them into a compact rendered string, and keeps the
session tail when over token budget (biased because tail is most at-risk
for context loss on /compact).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOOL_RESULT_CAP = 4000  # chars; above this we shim to a summary


@dataclass(frozen=True)
class WindowedTranscript:
    turns: list[dict[str, Any]]
    rendered: str
    turn_count: int


def read_windowed_transcript(path: Path, *, max_tokens: int) -> WindowedTranscript:
    """Load a JSONL transcript and return up to `max_tokens` worth of content,
    keeping the most recent turns if over budget.

    Missing file / empty file → empty WindowedTranscript (no crash).
    """
    if not path.exists():
        return WindowedTranscript(turns=[], rendered="", turn_count=0)

    turns: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            turns.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not turns:
        return WindowedTranscript(turns=[], rendered="", turn_count=0)

    rendered_parts = [_render_turn(t) for t in turns]

    # Token ≈ 4 chars heuristic; keep tail under budget.
    char_budget = max_tokens * 4
    total_chars = sum(len(p) for p in rendered_parts)
    if total_chars > char_budget:
        kept: list[str] = []
        total = 0
        for part in reversed(rendered_parts):
            if total + len(part) > char_budget and kept:
                break
            kept.append(part)
            total += len(part)
        kept.reverse()
        turns = turns[-len(kept):]
        rendered_parts = kept

    return WindowedTranscript(
        turns=turns,
        rendered="\n\n".join(rendered_parts),
        turn_count=len(turns),
    )


def _render_turn(turn: dict[str, Any]) -> str:
    t = turn.get("type", "")
    if t == "user":
        return f"[USER]\n{_extract_message_content(turn.get('message', {}))}"
    if t == "assistant":
        return f"[ASSISTANT]\n{_extract_message_content(turn.get('message', {}))}"
    if t == "tool_result":
        name = turn.get("tool_name", "?")
        content = str(turn.get("content", ""))
        if len(content) > _TOOL_RESULT_CAP:
            nlines = content.count("\n") + 1
            return f"[tool-result: {nlines} lines, {name}]"
        return f"[TOOL-RESULT {name}]\n{content}"
    return ""


def _extract_message_content(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return str(content)
