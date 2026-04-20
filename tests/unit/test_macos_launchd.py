from unittest.mock import MagicMock

from claude_almanac.platform.macos_launchd import LaunchdNotifier, LaunchdScheduler


def test_render_daily_plist_includes_StartCalendarInterval(tmp_path):
    s = LaunchdScheduler(agents_dir=tmp_path)
    plist = s._render_daily("com.claude-almanac.digest", ["echo", "hi"], 7)
    assert "com.claude-almanac.digest" in plist
    assert "<integer>7</integer>" in plist
    assert "<key>StartCalendarInterval</key>" in plist


def test_render_always_on_plist_includes_KeepAlive(tmp_path):
    s = LaunchdScheduler(agents_dir=tmp_path)
    plist = s._render_always_on("com.claude-almanac.server", ["echo", "hi"])
    assert "<key>KeepAlive</key>" in plist
    assert "<true/>" in plist


def test_render_always_on_plist_sets_ThrottleInterval(tmp_path):
    s = LaunchdScheduler(agents_dir=tmp_path)
    plist = s._render_always_on("com.claude-almanac.server", ["echo", "hi"])
    assert "<key>ThrottleInterval</key>" in plist
    assert "<integer>30</integer>" in plist


def test_install_daily_writes_file_and_calls_launchctl(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: calls.append(a[0]) or MagicMock(returncode=0))
    s = LaunchdScheduler(agents_dir=tmp_path)
    s.install_daily("com.claude-almanac.digest", ["echo", "hi"], 7)
    assert (tmp_path / "com.claude-almanac.digest.plist").exists()
    assert any("launchctl" in c and "load" in c for c in calls)


def test_notifier_uses_terminal_notifier_when_present(monkeypatch):
    called = []
    def which(_): return "/opt/homebrew/bin/terminal-notifier"
    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: called.append(a[0]) or MagicMock(returncode=0))
    LaunchdNotifier().notify("t", "m")
    assert "terminal-notifier" in called[0][0]


def test_notifier_falls_back_to_osascript(monkeypatch):
    called = []
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: called.append(a[0]) or MagicMock(returncode=0))
    LaunchdNotifier().notify("t", "m")
    assert "osascript" in called[0][0]
