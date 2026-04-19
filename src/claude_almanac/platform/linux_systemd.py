"""systemd --user Scheduler and notify-send Notifier."""
from __future__ import annotations

import shlex
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


class SystemdScheduler:
    def __init__(self, units_dir: Path | None = None):
        self.units_dir = units_dir or Path.home() / ".config" / "systemd" / "user"

    def _render_service(self, unit_name: str, cmd: list[str]) -> str:
        tmpl = _env.get_template("systemd.service.j2")
        return tmpl.render(
            unit_name=unit_name,
            exec_start=shlex.join(cmd),
            log_path=str(paths.logs_dir() / f"{unit_name}.log"),
        )

    def _render_daily_timer(self, unit_name: str, hour: int) -> str:
        tmpl = _env.get_template("systemd_daily.timer.j2")
        return tmpl.render(unit_name=unit_name, hour_padded=f"{hour:02d}")

    def _systemctl(self, *args: str) -> None:
        subprocess.run(
            ["systemctl", "--user", *args], check=False, capture_output=True
        )

    def install_daily(self, unit_name: str, cmd: list[str], hour: int) -> None:
        self.units_dir.mkdir(parents=True, exist_ok=True)
        (self.units_dir / f"{unit_name}.service").write_text(
            self._render_service(unit_name, cmd)
        )
        (self.units_dir / f"{unit_name}.timer").write_text(
            self._render_daily_timer(unit_name, hour)
        )
        self._systemctl("daemon-reload")
        self._systemctl("enable", "--now", f"{unit_name}.timer")

    def install_always_on(self, unit_name: str, cmd: list[str]) -> None:
        self.units_dir.mkdir(parents=True, exist_ok=True)
        svc = self._render_service(unit_name, cmd).replace(
            "Type=oneshot", "Type=simple\nRestart=on-failure"
        )
        (self.units_dir / f"{unit_name}.service").write_text(svc)
        self._systemctl("daemon-reload")
        self._systemctl("enable", "--now", f"{unit_name}.service")

    def uninstall(self, unit_name: str) -> None:
        self._systemctl("disable", "--now", f"{unit_name}.timer")
        self._systemctl("disable", "--now", f"{unit_name}.service")
        for suffix in (".service", ".timer"):
            p = self.units_dir / f"{unit_name}{suffix}"
            if p.exists():
                p.unlink()
        self._systemctl("daemon-reload")

    def status(self, unit_name: str) -> SchedulerStatus:
        timer_result = subprocess.run(
            ["systemctl", "--user", "is-active", f"{unit_name}.timer"],
            capture_output=True, text=True, check=False,
        )
        running = timer_result.stdout.strip() == "active"
        if not running:
            service_result = subprocess.run(
                ["systemctl", "--user", "is-active", f"{unit_name}.service"],
                capture_output=True, text=True, check=False,
            )
            running = service_result.stdout.strip() == "active"
        return SchedulerStatus(
            name=unit_name,
            running=running,
            last_exit_code=None,
        )


class SystemdNotifier:
    def notify(self, title: str, message: str, link: str | None = None) -> None:
        nn = shutil.which("notify-send")
        if not nn:
            return  # silent no-op if notify-send missing
        cmd = [nn, title, message]
        subprocess.run(cmd, check=False, capture_output=True)
