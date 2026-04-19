"""Curator worker: invoked via `python -m claude_almanac.core.curator`.

Reads recent conversation state, asks Haiku (via the local `claude -p` CLI)
what to save, applies decisions to markdown files + archive DB.

Ported from ~/.claude/memory-tools/curator-worker.py. Key changes:
- paths come from claude_almanac.core.paths (XDG-aware)
- embedder is pluggable via claude_almanac.embedders
- dedup threshold loaded from per-embedder profile (or config override)

The `_read_conversation_tail` function is intentionally a stub for v0.1 —
it only honors an explicit ``CLAUDE_ALMANAC_TRANSCRIPT`` env var. The
existing curator-worker.py has session-scraping logic; porting it is
tracked as follow-up work (see the Foundation plan "Known follow-up work"
section).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from importlib.resources import files
from pathlib import Path

from ..embedders import get_profile, make_embedder
from . import archive, config, dedup, paths

LOGGER = logging.getLogger("claude_almanac.curator")


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


def _apply_decisions(decisions: list[dict]) -> None:
    cfg = config.load()
    profile = get_profile(cfg.embedder.provider, cfg.embedder.model)
    threshold = cfg.thresholds.dedup_distance or profile.dedup_distance
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    for d in decisions:
        action = d.get("action")
        scope = d.get("scope", "project")
        scope_dir = (
            paths.global_memory_dir() if scope == "global" else paths.project_memory_dir()
        )
        scope_dir.mkdir(parents=True, exist_ok=True)
        db = scope_dir / "archive.db"
        archive.init(
            db,
            embedder_name=embedder.name,
            model=cfg.embedder.model,
            dim=embedder.dim,
            distance=embedder.distance,
        )

        if action == "write_md":
            slug = d["slug"]
            text = d["text"]
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
            text = d["text"]
            [vec] = embedder.embed([text])
            archive.insert_entry(
                db,
                text=text,
                kind=d.get("kind", "note"),
                source=d.get("source", "turn"),
                pinned=False,
                embedding=vec,
            )


def _read_conversation_tail() -> str:
    """Placeholder for conversation capture.

    In the existing memory-tools system this is done by scraping Claude
    Code's session log. For v0.1 the curator only runs if a transcript
    file is explicitly provided via the ``CLAUDE_ALMANAC_TRANSCRIPT`` env
    var; porting the session-scrape logic is tracked as follow-up work.
    """
    transcript = os.environ.get("CLAUDE_ALMANAC_TRANSCRIPT")
    if transcript and Path(transcript).exists():
        return Path(transcript).read_text()
    return ""


def main() -> None:
    _setup_logging()
    tail = _read_conversation_tail()
    if not tail.strip():
        LOGGER.info("curator: no conversation tail, skipping")
        return
    try:
        raw = _run_llm(tail)
        payload = json.loads(raw) if raw.strip() else {}
        decisions = payload.get("decisions", [])
        if decisions:
            _apply_decisions(decisions)
    except Exception:
        LOGGER.exception("curator main loop failed")


if __name__ == "__main__":
    main()
