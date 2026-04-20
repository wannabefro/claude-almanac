"""Worker spawned by the SessionStart upgrade hook.

Runs `uv tool upgrade claude-almanac` against the public PyPI index
(bypassing any pinned corporate mirror that might not carry the package)
and records the exit code to `upgrade.status.json` so the next SessionStart
can surface a failed background upgrade instead of silently retrying.

Invoked as::

    python -m claude_almanac.hooks.upgrade_runner <target_version>

Status file format::

    {"ts": <epoch>, "exit": <int>, "target": "<version>"}
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from claude_almanac.core import paths

_INDEX = "https://pypi.org/simple/"


def _run(target_version: str) -> int:
    log_path = paths.logs_dir() / "upgrade.log"
    status_path = paths.logs_dir() / "upgrade.status.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(
            f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} upgrading to "
            f"{target_version} ---\n".encode()
        )
        log.flush()
        try:
            result = subprocess.run(
                ["uv", "tool", "upgrade", "--default-index", _INDEX,
                 "claude-almanac"],
                stdout=log, stderr=log, check=False,
            )
            exit_code = result.returncode
        except (OSError, subprocess.SubprocessError) as e:
            log.write(f"runner: launch failed: {e}\n".encode())
            exit_code = 127
    status_path.write_text(json.dumps({
        "ts": int(time.time()),
        "exit": exit_code,
        "target": target_version,
    }))
    return exit_code


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(2)
    sys.exit(_run(sys.argv[1]))


if __name__ == "__main__":
    main()
