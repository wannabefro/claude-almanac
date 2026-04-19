"""Stop hook entrypoint. Forks a background curator worker and exits fast
so Claude Code's Stop handler isn't blocked."""
from __future__ import annotations

import subprocess
import sys


def _spawn_worker() -> None:
    subprocess.Popen(
        [sys.executable, "-m", "claude_almanac.core.curator"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def main() -> None:
    _spawn_worker()


if __name__ == "__main__":
    main()
