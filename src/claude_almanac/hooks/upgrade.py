"""SessionStart hook: detect drift between the installed claude-almanac CLI
version and the plugin's declared version, print a notice, and optionally
background an `uv tool upgrade` when the user has opted in via `auto_upgrade`.

This hook is the bridge between two independent update surfaces:
  - `/plugin update claude-almanac` refreshes this plugin directory.
  - `uv tool upgrade claude-almanac` refreshes the Python package / CLI.

Without this hook, a user who only runs `/plugin update` would get new
commands and hooks.json referencing a possibly-older CLI, leading to confusing
half-states. The hook keeps both halves in sync without forcing the user to
remember the second command.

Auto-upgrade flow:
  1. On drift, look at `upgrade.status.json` first. If the previous attempt
     for this plugin version failed, surface the failure and DO NOT retry.
  2. Otherwise spawn `upgrade_runner.py` detached; it runs uv against the
     public index and writes the status file for the next session to read.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path


def _installed_version() -> str | None:
    try:
        return _pkg_version("claude-almanac")
    except PackageNotFoundError:
        return None


def _plugin_version(plugin_root: str) -> str | None:
    try:
        with (Path(plugin_root) / "plugin.json").open() as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    v = raw.get("version")
    return v if isinstance(v, str) else None


def _detect_uv_install() -> bool:
    """True when the running CLI is installed via `uv tool install`."""
    return "uv/tools/claude-almanac" in sys.executable


def _load_status(status_path: Path) -> dict[str, object] | None:
    try:
        return json.loads(status_path.read_text())  # type: ignore[no-any-return]
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        return  # Not running in plugin context; nothing to reconcile.

    plugin_v = _plugin_version(plugin_root)
    cli_v = _installed_version()
    if not plugin_v or not cli_v or plugin_v == cli_v:
        return

    from claude_almanac.core import config as _config
    from claude_almanac.core import paths

    try:
        cfg = _config.load()
    except Exception:
        return

    if not cfg.auto_upgrade:
        sys.stdout.write(
            f"claude-almanac: plugin v{plugin_v} > CLI v{cli_v}. "
            f"Run `uv tool upgrade claude-almanac` to sync.\n"
        )
        return

    if not _detect_uv_install():
        sys.stdout.write(
            f"claude-almanac: plugin v{plugin_v} > CLI v{cli_v}; "
            f"auto_upgrade only supports uv tool installs. Upgrade manually.\n"
        )
        return

    log = paths.logs_dir() / "upgrade.log"
    status_path = paths.logs_dir() / "upgrade.status.json"

    # If a prior auto-upgrade attempt for this exact target failed, surface
    # the failure and bail — don't spawn another doomed subprocess every
    # session.
    prev = _load_status(status_path)
    if (
        isinstance(prev, dict)
        and prev.get("target") == plugin_v
        and isinstance(prev.get("exit"), int)
        and prev.get("exit") != 0
    ):
        ts_raw = prev.get("ts")
        ts = ts_raw if isinstance(ts_raw, int) else 0
        age_hours = max(0, (int(time.time()) - ts) // 3600)
        sys.stdout.write(
            f"claude-almanac: last auto-upgrade to v{plugin_v} failed "
            f"~{age_hours}h ago (exit={prev['exit']}). See {log}. "
            f"Run manually: "
            f"`uv tool upgrade --default-index https://pypi.org/simple/ "
            f"claude-almanac`\n"
        )
        return

    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [sys.executable, "-m",
             "claude_almanac.hooks.upgrade_runner", plugin_v],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        sys.stdout.write(
            f"claude-almanac: upgrade launch failed ({e}); "
            f"run `uv tool upgrade claude-almanac` manually.\n"
        )
        return
    sys.stdout.write(
        f"claude-almanac: upgrading CLI v{cli_v} -> v{plugin_v} in background "
        f"(log: {log}).\n"
    )


if __name__ == "__main__":
    main()
