"""Curator worker: invoked via `python -m claude_almanac.core.curator`.

Reads recent conversation state, asks Haiku (via the local `claude -p` CLI)
what to save, applies decisions to markdown files + archive DB.

Ported from ~/.claude/memory-tools/curator-worker.py. Key changes:
- paths come from claude_almanac.core.paths (XDG-aware)
- embedder is pluggable via claude_almanac.embedders
- dedup threshold loaded from per-embedder profile (or config override)

The transcript reader parses Claude Code's JSONL session transcript. It
honors ``CLAUDE_ALMANAC_TRANSCRIPT`` (explicit override for CLI/testing)
and ``CLAUDE_ALMANAC_HOOK_TRANSCRIPT`` (set by the Stop hook when forking
the worker).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any

from claude_almanac.embedders import get_profile, make_embedder

from . import archive, config, dedup, paths

LOGGER = logging.getLogger("claude_almanac.curator")

MAX_TRANSCRIPT_CHARS = 120_000   # Haiku context budget minus prompt overhead


def _setup_logging() -> None:
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(paths.logs_dir() / "curator.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def _prompt_template() -> str:
    return files("claude_almanac.core.assets").joinpath("curator-prompt.md").read_text()


def _run_llm(conversation_tail: str) -> str:
    """Invoke the local ``claude -p --model haiku`` CLI with the curator prompt."""
    prompt = f"{_prompt_template()}\n\n---\n\n{conversation_tail}"
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", "haiku"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        LOGGER.warning("curator LLM call failed: %s", e)
        return "{}"


def _apply_decisions(decisions: list[dict[str, Any]]) -> None:
    cfg = config.load()
    profile = get_profile(cfg.embedder.provider, cfg.embedder.model)
    threshold = cfg.thresholds.dedup_distance or profile.dedup_distance
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    scope_dirs = {
        paths.global_memory_dir(): paths.global_memory_dir() / "archive.db",
        paths.project_memory_dir(): paths.project_memory_dir() / "archive.db",
    }
    for scope_dir, db in scope_dirs.items():
        scope_dir.mkdir(parents=True, exist_ok=True)
        try:
            archive.init(
                db,
                embedder_name=embedder.name,
                model=cfg.embedder.model,
                dim=embedder.dim,
                distance=embedder.distance,
            )
        except archive.EmbedderMismatch as e:
            LOGGER.error("embedder mismatch in %s — re-index required: %s", db, e)
            return

    for d in decisions:
        action = d.get("action")
        scope = d.get("scope", "project")
        scope_dir = (
            paths.global_memory_dir() if scope == "global" else paths.project_memory_dir()
        )
        db = scope_dir / "archive.db"

        if action == "write_md":
            slug = d.get("slug")
            text = d.get("text")
            if not slug or not text:
                LOGGER.warning(
                    "curator: dropping write_md with missing slug/text: %s",
                    {k: v for k, v in d.items() if k != "text"},
                )
                continue
            [vec] = embedder.embed([text])
            dup_slug, dist = dedup.find_dup_slug(db=db, embedding=vec, threshold=threshold)
            if dup_slug:
                LOGGER.info("dedup: %r -> %r (distance=%.3f)", slug, dup_slug, dist)
                slug = dup_slug
            else:
                LOGGER.info("dedup-miss: nearest md distance=%s", dist)
            target = scope_dir / slug
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            archive.insert_entry(
                db,
                text=text,
                kind=d.get("kind", "reference"),
                source=f"md:{slug}",
                pinned=True,
                embedding=vec,
            )

        elif action == "archive_turn":
            text = d.get("text")
            if not text:
                LOGGER.warning("curator: dropping archive_turn with missing text")
                continue
            [vec] = embedder.embed([text])
            archive.insert_entry(
                db,
                text=text,
                kind=d.get("kind", "note"),
                source=d.get("source", "turn"),
                pinned=False,
                embedding=vec,
            )

        else:
            LOGGER.info("curator: ignoring decision with action=%r", action)


def _iter_turns(transcript_path: str) -> Iterator[tuple[str, str]]:
    """Yield (role, text) for each user/assistant/compaction/subagent_stop event.

    Roles beyond user/assistant:
      - "compaction"     — {"type": "summary", "summary": "..."} events
      - "subagent_stop"  — {"type": "subagent_stop", "summary": "..."} events

    Ported from memory-tools/curator-worker.py. Handles:
    - string content
    - list-of-parts content (extracts type=text parts, skips tool_use/tool_result)
    - malformed lines (logged-and-skipped, not raised)
    """
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev_type = ev.get("type")
                if ev_type == "summary":
                    summary_text = ev.get("summary", "")
                    if summary_text:
                        yield "compaction", summary_text
                    continue
                if ev_type == "subagent_stop":
                    summary_text = ev.get("summary", "")
                    if summary_text:
                        yield "subagent_stop", summary_text
                    continue
                msg = ev.get("message") or {}
                role = msg.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    text = "\n".join(parts)
                if not text.strip():
                    continue
                yield role, text
    except OSError as e:
        LOGGER.warning("transcript read failed: %s", e)


def _parse_full_transcript(transcript_path: str) -> str:
    """Concatenate all user/assistant turns with <USER>/<ASSISTANT> tags.

    Tail-truncates when the result would exceed MAX_TRANSCRIPT_CHARS.
    """
    chunks: list[str] = []
    for role, text in _iter_turns(transcript_path):
        label = "USER" if role == "user" else "ASSISTANT"
        chunks.append(f"<{label}>\n{text}\n</{label}>")
    full = "\n\n".join(chunks)
    if len(full) > MAX_TRANSCRIPT_CHARS:
        full = "...(earlier turns truncated)...\n\n" + full[-MAX_TRANSCRIPT_CHARS:]
    return full


def _read_conversation_tail() -> str:
    """Read the conversation tail for the curator.

    Prefers ``CLAUDE_ALMANAC_TRANSCRIPT`` (explicit override for CLI/testing),
    falls back to ``CLAUDE_ALMANAC_HOOK_TRANSCRIPT`` (set by the Stop hook
    when forking the worker). Returns empty string if neither is set or
    the path doesn't exist.
    """
    for env_var in ("CLAUDE_ALMANAC_TRANSCRIPT", "CLAUDE_ALMANAC_HOOK_TRANSCRIPT"):
        path = os.environ.get(env_var)
        if path and Path(path).exists():
            return _parse_full_transcript(path)
    return ""


def _strip_json_fence(raw: str) -> str:
    """Strip a ```json ... ``` (or bare ```) markdown fence from Haiku output.

    Haiku occasionally wraps its JSON decision payload in a code fence even
    when the prompt asks for raw JSON. Stripping here lets the parser accept
    the fenced form without losing the payload.
    """
    s = raw.strip()
    if not s.startswith("```"):
        return s
    # Drop opening fence line (```json / ```)
    first_newline = s.find("\n")
    if first_newline == -1:
        return s
    inner = s[first_newline + 1 :]
    if inner.rstrip().endswith("```"):
        inner = inner.rstrip()
        inner = inner[: -len("```")]
    return inner.strip()


def _parse_decisions(raw: str) -> list[dict[str, Any]]:
    """Parse Haiku's decision payload, tolerating three observed shapes.

    Haiku has been seen to return any of:
      - `{"decisions": [ ... ]}` — the documented contract
      - `[ ... ]`                — a bare list of decisions
      - ````json\n...\n````      — any of the above wrapped in a code fence

    Returns the decision list, or [] if the payload is unparseable or empty.
    Never raises — caller (main) relies on a clean list contract.
    """
    cleaned = _strip_json_fence(raw)
    if not cleaned:
        return []
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        LOGGER.warning("curator: LLM returned non-JSON: %.200s", raw)
        return []
    if isinstance(payload, list):
        return [d for d in payload if isinstance(d, dict)]
    if isinstance(payload, dict):
        decisions = payload.get("decisions", [])
        if isinstance(decisions, list):
            return [d for d in decisions if isinstance(d, dict)]
    LOGGER.warning("curator: unexpected payload shape: %s", type(payload).__name__)
    return []


def main() -> None:
    _setup_logging()
    tail = _read_conversation_tail()
    if not tail.strip():
        LOGGER.info("curator: no conversation tail, skipping")
        return
    try:
        raw = _run_llm(tail)
        decisions = _parse_decisions(raw)
        if decisions:
            _apply_decisions(decisions)
    except Exception:
        LOGGER.exception("curator main loop failed")


if __name__ == "__main__":
    main()
