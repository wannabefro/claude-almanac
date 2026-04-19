"""launchd-based Scheduler and terminal-notifier/osascript-based Notifier."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ..core import paths
from .base import SchedulerStatus


_env = Environment(
    loader=PackageLoader("claude_almanac.platform", "templates"),
    autoescape=select_autoescape(),
)


class LaunchdScheduler:
    def __init__(self, agents_dir: Path | None = None):
        self.agents_dir = agents_dir or Path.home() / "Library" / "LaunchAgents"

    def _render_daily(self, label: str, cmd: list[str], hour: int) -> str:
        tmpl = _env.get_template("launchd_daily.plist.j2")
        return tmpl.render(
            label=label, program_arguments=cmd, hour=hour,
            log_path=str(paths.logs_dir() / f"{label}.log"),
        )

    def _render_always_on(self, label: str, cmd: list[str]) -> str:
        tmpl = _env.get_template("launchd_always_on.plist.j2")
        return tmpl.render(
            label=label, program_arguments=cmd,
            log_path=str(paths.logs_dir() / f"{label}.log"),
        )

    def _write_and_load(self, label: str, content: str) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        path = self.agents_dir / f"{label}.plist"
        path.write_text(content)
        subprocess.run(["launchctl", "unload", str(path)], check=False,
                       capture_output=True)
        subprocess.run(["launchctl", "load", str(path)], check=False,
                       capture_output=True)

    def install_daily(self, unit_name: str, cmd: list[str], hour: int) -> None:
        self._write_and_load(unit_name, self._render_daily(unit_name, cmd, hour))

    def install_always_on(self, unit_name: str, cmd: list[str]) -> None:
        self._write_and_load(unit_name, self._render_always_on(unit_name, cmd))

    def uninstall(self, unit_name: str) -> None:
        path = self.agents_dir / f"{unit_name}.plist"
        if path.exists():
            subprocess.run(["launchctl", "unload", str(path)], check=False,
                           capture_output=True)
            path.unlink()

    def status(self, unit_name: str) -> SchedulerStatus:
        result = subprocess.run(
            ["launchctl", "list", unit_name],
            capture_output=True, text=True, check=False,
        )
        return SchedulerStatus(name=unit_name, running=result.returncode == 0,
                               last_exit_code=None)


class LaunchdNotifier:
    def notify(self, title: str, message: str, link: str | None = None) -> None:
        tn = shutil.which("terminal-notifier")
        if tn:
            cmd = [tn, "-title", title, "-message", message]
            if link:
                cmd += ["-open", link]
            subprocess.run(cmd, check=False, capture_output=True)
            return
        script = f'display notification {message!r} with title {title!r}'
        subprocess.run(["osascript", "-e", script], check=False,
                       capture_output=True)
