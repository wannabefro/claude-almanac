"""SessionEnd + PreCompact hook entrypoint.

Parses the stdin payload, forks a detached background worker, returns fast.
Never blocks the hook.
"""
from __future__ import annotations

import logging
import subprocess
import sys

from claude_almanac.core.config import load as load_config
from claude_almanac.rollups.triggers import RollupEvent, parse_hook_event

LOGGER = logging.getLogger(__name__)


def run_hook(stdin_payload: str) -> None:
    ev = parse_hook_event(stdin_payload)
    if ev is None:
        return
    try:
        cfg = load_config()
    except Exception as e:
        LOGGER.info("rollup-hook: cfg load failed: %s", e)
        return
    if not cfg.rollup.enabled:
        return
    _spawn_background(ev)


def _spawn_background(ev: RollupEvent) -> None:
    cmd = [
        sys.executable, "-m", "claude_almanac.rollups.runner",
        "--trigger", ev.trigger,
        "--transcript", str(ev.transcript_path),
        "--session-id", ev.session_id,
        "--cwd", str(ev.cwd),
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> int:
    payload = sys.stdin.read()
    run_hook(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
