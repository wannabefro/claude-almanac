"""UserPromptSubmit hook entrypoint. Reads JSON {prompt: ...} from stdin,
prints context to stdout (which Claude Code injects into the turn)."""
from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from claude_almanac.core import retrieve as core_retrieve

LOGGER = logging.getLogger(__name__)


def _maybe_fire_idle_rollup(
    *,
    current_session_id: str,
    idle_threshold_minutes: int,
    cwd: Path,
) -> None:
    """First-prompt-of-new-session check: if the prior session went stale
    without a rollup, spawn one retroactively. Never blocks the hook.
    """
    stale = _stale_prior_session(current_session_id, idle_threshold_minutes, cwd)
    if stale is None:
        return
    prior_transcript, prior_session_id = stale
    if _has_rollup(prior_session_id):
        return
    _spawn_idle_rollup(prior_transcript, prior_session_id, cwd)


def _stale_prior_session(
    current_session_id: str,
    idle_threshold_minutes: int,
    cwd: Path,
) -> tuple[Path, str] | None:
    """Return (path, session_id) for the most-recent other transcript in
    this cwd's encoded project dir, if its mtime is older than the threshold.
    """
    tdir = _transcripts_dir_for_cwd(cwd)
    if tdir is None or not tdir.exists():
        return None
    threshold_ts = time.time() - idle_threshold_minutes * 60
    candidates = [
        p for p in tdir.glob("*.jsonl")
        if p.stem != current_session_id and p.stat().st_mtime < threshold_ts
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    return (best, best.stem)


def _transcripts_dir_for_cwd(cwd: Path) -> Path | None:
    """Claude Code encodes cwd path into ~/.claude/projects/<encoded>."""
    encoded = str(cwd).replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded


def _has_rollup(session_id: str) -> bool:
    """Check archive.db for an existing rollup with this session_id. Fail-safe:
    return True on any error so we don't spam runner invocations.
    """
    try:
        from claude_almanac.core.paths import project_memory_dir

        db = project_memory_dir() / "archive.db"
        if not db.exists():
            return True  # no archive yet — don't try
        conn = sqlite3.connect(db)
        try:
            row = conn.execute(
                "SELECT 1 FROM rollups WHERE session_id=? LIMIT 1", (session_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return True


def _spawn_idle_rollup(transcript: Path, session_id: str, cwd: Path) -> None:
    """Detached fork of the rollup runner with trigger=idle."""
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "claude_almanac.rollups.runner",
            "--trigger",
            "idle",
            "--transcript",
            str(transcript),
            "--session-id",
            session_id,
            "--cwd",
            str(cwd),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return

    # v0.3.2: idle-fallback rollup check for prior session.
    # Parse session_id and cwd from payload; use sensible defaults if not present.
    session_id = payload.get("session_id", "")
    cwd_str = payload.get("cwd", "")
    cwd = Path(cwd_str) if cwd_str else Path.cwd()

    # Only attempt if we can load config to check rollup.enabled.
    try:
        from claude_almanac.core.config import load as load_config
        cfg = load_config()
        if cfg.rollup.enabled:
            _maybe_fire_idle_rollup(
                current_session_id=session_id,
                idle_threshold_minutes=cfg.rollup.idle_threshold_minutes,
                cwd=cwd,
            )
    except Exception as e:
        LOGGER.debug("idle-rollup check failed: %s", e)

    prompt = payload.get("prompt", "")
    text = core_retrieve.run(prompt)
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
