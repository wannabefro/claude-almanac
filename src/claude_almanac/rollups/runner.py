"""Background worker: build cfg, curator, embedder; invoke generator; persist.

Invoked via `python -m claude_almanac.rollups.runner --trigger ... --transcript ...`
from hooks/rollup.py. Never expected to block anything — the hook already
detached this process.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from claude_almanac.core.archive import (
    insert_rollup,
    lookup_entry_id_by_slug,
)
from claude_almanac.core.config import Config
from claude_almanac.core.config import load as load_config
from claude_almanac.core.paths import project_memory_dir
from claude_almanac.curators.factory import make_curator
from claude_almanac.edges.store import insert_edge
from claude_almanac.embedders.factory import make_embedder
from claude_almanac.rollups.generator import Rollup, RollupGenerator

LOGGER = logging.getLogger(__name__)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", required=True)
    ap.add_argument("--transcript", required=True, type=Path)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--cwd", required=True, type=Path)
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.rollup.enabled:
        return 0

    curator_cfg = _override_curator(cfg, cfg.rollup.provider, cfg.rollup.model)
    curator = make_curator(curator_cfg)
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    gen = RollupGenerator(
        curator=curator,
        embedder=embedder,
        memories_for_window=_memories_for_window,
        git_commits_for_window=_git_commits_for_window,
        max_transcript_tokens=cfg.rollup.max_transcript_tokens,
    )

    # project_key() uses cwd internally (git rev-parse), so we chdir temporarily
    import os
    orig_cwd = os.getcwd()
    try:
        os.chdir(args.cwd)
        from claude_almanac.core.paths import project_key
        repo_key = project_key()
    finally:
        os.chdir(orig_cwd)

    branch = _current_branch(args.cwd)

    rollup: Rollup | None = gen.generate(
        transcript_path=args.transcript,
        session_id=args.session_id,
        repo_key=repo_key,
        branch=branch,
        trigger=args.trigger,
        min_turns=cfg.rollup.min_turns,
    )
    if rollup is None:
        return 0

    db = project_memory_dir() / "archive.db"
    rid = insert_rollup(
        db,
        session_id=rollup.session_id,
        repo_key=rollup.repo_key,
        branch=rollup.branch,
        started_at=rollup.started_at,
        ended_at=rollup.ended_at,
        turn_count=rollup.turn_count,
        trigger=rollup.trigger,
        narrative=rollup.narrative,
        decisions=json.dumps(rollup.decisions),
        artifacts=json.dumps(rollup.artifacts),
        embedding=rollup.embedding,
    )
    if rid is None:
        LOGGER.info("rollup: duplicate (session_id, trigger) — skipping persist")
        return 0

    # Insert produced_by edges to memories written during the window.
    conn = sqlite3.connect(str(db))
    try:
        for slug in rollup.artifacts.get("memories", []):
            entry_id = lookup_entry_id_by_slug(conn, slug)
            if entry_id is None:
                continue
            insert_edge(
                conn,
                rid,
                "rollup@project",
                entry_id,
                "entry@project",
                "produced_by",
                "rollup_generator",
            )
    finally:
        conn.close()

    return 0


def _override_curator(
    cfg: Config, provider: str | None, model: str | None = None,
) -> Config:
    """Return cfg with curator.provider / curator.model overridden for rollups.

    Either override can be None (no change on that axis). This lets callers
    mix "same provider, different model" (e.g. cfg.curator=ollama+gemma4:e4b
    but rollups want ollama+qwen2.5:7b) without touching the curator config.
    """
    if provider is None and model is None:
        return cfg
    curator_overrides: dict[str, Any] = {}
    if provider is not None:
        curator_overrides["provider"] = provider
    if model is not None:
        curator_overrides["model"] = model
    return dataclasses.replace(
        cfg, curator=dataclasses.replace(cfg.curator, **curator_overrides),
    )


def _current_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or None
    except Exception:
        return None


def _memories_for_window(started_at: int, ended_at: int, repo_key: str) -> list[dict[str, Any]]:
    db = project_memory_dir() / "archive.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT text, source FROM entries WHERE created_at BETWEEN ? AND ?",
            (started_at, ended_at),
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for text, source in rows:
        slug = source[3:] if isinstance(source, str) and source.startswith("md:") else source
        out.append({"slug": slug, "body": text})
    return out


def _git_commits_for_window(started_at: int, ended_at: int) -> list[str]:
    try:
        out = subprocess.check_output(
            [
                "git", "log", "--pretty=format:%h %s",
                f"--since=@{started_at}", f"--until=@{ended_at}",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [line for line in out.splitlines() if line.strip()]
    except Exception:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
