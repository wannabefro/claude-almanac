import subprocess
from unittest.mock import MagicMock

import pytest

from claude_almanac.digest.qa import fast


def test_fast_answer_returns_no_activity_stub(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [],
    )
    out = fast.answer_fast(
        question="what?", digest_markdown="# empty", date="2026-04-19",
    )
    assert "No recent activity" in out


def test_fast_answer_synthesizes_via_claude(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [{
            "repo": "r", "sha": "abcdef1234", "subject": "feat: x",
            "snippet": "feat: x\n\ndiff ...", "distance": 0.1,
        }],
    )
    captured = {}
    def fake_run(argv, input, **kw):
        captured["argv"] = argv
        captured["stdin"] = input
        m = MagicMock()
        m.returncode = 0
        m.stdout = "the answer"
        m.stderr = ""
        return m
    monkeypatch.setattr("subprocess.run", fake_run)
    out = fast.answer_fast(
        question="what?", digest_markdown="# ok", date="2026-04-19",
    )
    assert out == "the answer"
    assert captured["argv"] == ["claude", "-p", "--model", "haiku"]
    assert "feat: x" in captured["stdin"]


def test_fast_raises_when_claude_binary_missing(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [{
            "repo": "r", "sha": "abcdef1234", "subject": "feat: x",
            "snippet": "feat: x\n\ndiff ...", "distance": 0.1,
        }],
    )
    def fake_run(*args, **kwargs):
        raise FileNotFoundError(2, "No such file", "claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="claude binary not found"):
        fast.answer_fast(question="x", digest_markdown="y", date="2026-04-19")
