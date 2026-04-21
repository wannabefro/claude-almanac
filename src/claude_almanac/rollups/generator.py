"""Rollup producer: transcript + metadata → LLM → structured Rollup."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from claude_almanac.rollups.transcript import read_windowed_transcript

LOGGER = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "assets" / "rollup-prompt.md"


@dataclass
class Rollup:
    session_id: str
    repo_key: str
    branch: str | None
    started_at: int
    ended_at: int
    turn_count: int
    trigger: str
    narrative: str
    decisions: list[dict[str, Any]]
    artifacts: dict[str, Any]
    embedding: list[float]


class _CuratorLike(Protocol):
    def invoke(self, system_prompt: str, user_turn: str) -> str: ...


class _EmbedderLike(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RollupGenerator:
    """Transcript → LLM → structured Rollup object.

    Dependency-injects curator + embedder + data-lookup callables so unit tests
    can run fully mocked and integration tests can wire real providers.
    """

    def __init__(
        self,
        *,
        curator: _CuratorLike,
        embedder: _EmbedderLike,
        memories_for_window: Callable[[int, int, str], list[dict[str, Any]]],
        git_commits_for_window: Callable[[int, int], list[str]],
        max_transcript_tokens: int = 32000,
    ) -> None:
        self._curator = curator
        self._embedder = embedder
        self._memories_for_window = memories_for_window
        self._git_commits_for_window = git_commits_for_window
        self._max_tokens = max_transcript_tokens

    def generate(
        self,
        *,
        transcript_path: Path,
        session_id: str,
        repo_key: str,
        branch: str | None,
        trigger: str,
        min_turns: int = 3,
    ) -> Rollup | None:
        """Produce a Rollup for the session, or None to skip."""
        windowed = read_windowed_transcript(transcript_path, max_tokens=self._max_tokens)
        if windowed.turn_count < min_turns:
            LOGGER.info("rollup: skipping (turns=%d < min=%d)",
                        windowed.turn_count, min_turns)
            return None

        started_at, ended_at = _session_bounds(windowed.turns)
        memories = self._memories_for_window(started_at, ended_at, repo_key)
        commits = self._git_commits_for_window(started_at, ended_at)
        artifacts = {
            "files": [],
            "commits": commits,
            "memories": [m["slug"] for m in memories],
        }

        prompt = _render_prompt({
            "TRANSCRIPT": windowed.rendered,
            "MEMORIES_WRITTEN": _format_memories(memories),
            "COMMITS": "\n".join(commits) or "(none)",
            "ARTIFACTS": json.dumps(artifacts),
        })
        raw = self._curator.invoke(prompt, user_turn="")

        payload = _parse_rollup_output(raw)
        if payload is None:
            return None
        narrative = payload.get("narrative", "").strip()
        if not narrative:
            LOGGER.warning("rollup: empty narrative; dropping")
            return None

        embedding = self._embedder.embed([narrative])[0]

        return Rollup(
            session_id=session_id, repo_key=repo_key, branch=branch,
            started_at=started_at, ended_at=ended_at,
            turn_count=windowed.turn_count, trigger=trigger,
            narrative=narrative,
            decisions=payload.get("decisions", []) or [],
            artifacts=payload.get("artifacts", artifacts) or artifacts,
            embedding=embedding,
        )


def _render_prompt(vars: dict[str, str]) -> str:
    template = _PROMPT_PATH.read_text()
    for k, v in vars.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def _parse_rollup_output(raw: str) -> dict[str, Any] | None:
    """Tolerate code fences, trailing whitespace. Return None on unparseable."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Drop opening fence line
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        cleaned = "\n".join(lines)
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        LOGGER.warning("rollup: non-JSON output (len=%d): %s", len(raw), raw[:500])
        return None
    if not isinstance(payload, dict):
        LOGGER.warning("rollup: non-object output type=%s", type(payload).__name__)
        return None
    return payload


def _session_bounds(turns: list[dict[str, Any]]) -> tuple[int, int]:
    timestamps = [int(t["timestamp"]) for t in turns
                  if isinstance(t.get("timestamp"), (int, float))]
    if timestamps:
        return min(timestamps), max(timestamps)
    now = int(time.time())
    return now, now


def _format_memories(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "(none)"
    return "\n\n".join(
        f"- {m.get('slug', '?')}\n  {(m.get('body') or m.get('text') or '')[:400]}"
        for m in memories
    )
