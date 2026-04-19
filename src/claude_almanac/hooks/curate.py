"""Stop hook entrypoint. Forks a background curator worker and exits fast
so Claude Code's Stop handler isn't blocked."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _spawn_worker(transcript_path: str | None = None) -> None:
    env = os.environ.copy()
    if transcript_path:
        env["CLAUDE_ALMANAC_HOOK_TRANSCRIPT"] = transcript_path
    subprocess.Popen(
        [sys.executable, "-m", "claude_almanac.core.curator"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=env,
    )


def main() -> None:
    transcript_path: str | None = None
    try:
        hook_input = json.load(sys.stdin)
        transcript_path = hook_input.get("transcript_path")
    except (json.JSONDecodeError, ValueError):
        # Hook-input absent (e.g. when run outside Claude Code) — spawn anyway;
        # the worker will read CLAUDE_ALMANAC_TRANSCRIPT if set.
        pass
    _spawn_worker(transcript_path)


if __name__ == "__main__":
    main()
