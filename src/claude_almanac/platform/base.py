"""OS-agnostic Scheduler and Notifier protocols + autoselect factories."""
from __future__ import annotations

import platform as _platform
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SchedulerStatus:
    name: str
    running: bool
    last_exit_code: int | None


@runtime_checkable
class Scheduler(Protocol):
    def install_daily(self, unit_name: str, cmd: list[str], hour: int) -> None: ...
    def install_always_on(self, unit_name: str, cmd: list[str]) -> None: ...
    def uninstall(self, unit_name: str) -> None: ...
    def status(self, unit_name: str) -> SchedulerStatus: ...


@runtime_checkable
class Notifier(Protocol):
    def notify(self, title: str, message: str, link: str | None = None) -> None: ...


def get_scheduler() -> Scheduler:
    system = _platform.system()
    if system == "Darwin":
        from .macos_launchd import LaunchdScheduler
        return LaunchdScheduler()
    if system == "Linux":
        from .linux_systemd import SystemdScheduler
        return SystemdScheduler()
    raise RuntimeError(f"Unsupported platform: {system}")


def get_notifier() -> Notifier:
    system = _platform.system()
    if system == "Darwin":
        from .macos_launchd import LaunchdNotifier
        return LaunchdNotifier()
    if system == "Linux":
        from .linux_systemd import SystemdNotifier
        return SystemdNotifier()
    raise RuntimeError(f"Unsupported platform: {system}")
