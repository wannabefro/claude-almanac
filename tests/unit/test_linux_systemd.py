from unittest.mock import MagicMock

from claude_almanac.platform.linux_systemd import SystemdNotifier, SystemdScheduler


def test_render_service_file(tmp_path):
    s = SystemdScheduler(units_dir=tmp_path)
    svc = s._render_service("claude-almanac-digest", ["/usr/bin/echo", "hi"])
    assert "[Service]" in svc
    assert "ExecStart=/usr/bin/echo hi" in svc


def test_render_timer_file(tmp_path):
    s = SystemdScheduler(units_dir=tmp_path)
    tmr = s._render_daily_timer("claude-almanac-digest", 7)
    assert "[Timer]" in tmr
    assert "OnCalendar=*-*-* 07:00:00" in tmr


def test_install_daily_writes_units_and_starts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: calls.append(a[0]) or MagicMock(returncode=0),
    )
    s = SystemdScheduler(units_dir=tmp_path)
    s.install_daily("claude-almanac-digest", ["/bin/echo", "hi"], 7)
    assert (tmp_path / "claude-almanac-digest.service").exists()
    assert (tmp_path / "claude-almanac-digest.timer").exists()
    assert any(
        "systemctl" in c and "enable" in c and "--now" in c for c in calls
    )


def test_notifier_uses_notify_send(monkeypatch):
    called = []
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: called.append(a[0]) or MagicMock(returncode=0),
    )
    SystemdNotifier().notify("t", "m")
    assert "notify-send" in called[0][0]
