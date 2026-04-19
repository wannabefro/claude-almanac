from unittest.mock import MagicMock

from claude_almanac.digest import notify as digest_notify


def test_notify_delegates_to_platform(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.digest.notify.get_notifier", lambda: fake,
    )
    ok = digest_notify.notify(
        title="t", message="m", open_url="http://x",
    )
    fake.notify.assert_called_once_with("t", "m", link="http://x")
    assert ok is True


def test_notify_returns_false_on_platform_error(monkeypatch):
    fake = MagicMock()
    fake.notify.side_effect = RuntimeError("no notifier")
    monkeypatch.setattr(
        "claude_almanac.digest.notify.get_notifier", lambda: fake,
    )
    ok = digest_notify.notify(title="t", message="m", open_url="http://x")
    assert ok is False
