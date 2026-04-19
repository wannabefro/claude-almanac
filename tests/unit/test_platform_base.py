from dataclasses import dataclass

from claude_almanac.platform.base import Notifier, Scheduler, SchedulerStatus


@dataclass
class FakeScheduler:
    calls: list = None
    def __post_init__(self):
        self.calls = []
    def install_daily(self, unit_name, cmd, hour):
        self.calls.append(("daily", unit_name, cmd, hour))
    def install_always_on(self, unit_name, cmd):
        self.calls.append(("always", unit_name, cmd))
    def uninstall(self, unit_name):
        self.calls.append(("uninstall", unit_name))
    def status(self, unit_name):
        return SchedulerStatus(name=unit_name, running=True, last_exit_code=0)


def test_scheduler_protocol_accepts_fake():
    s: Scheduler = FakeScheduler()
    s.install_daily("com.x.y", ["echo"], 7)
    assert s.calls[0][0] == "daily"


def test_notifier_protocol_accepts_fake():
    class N:
        def notify(self, title, message, link=None):
            self.last = (title, message, link)
    n: Notifier = N()
    n.notify("t", "m")
    assert n.last == ("t", "m", None)
