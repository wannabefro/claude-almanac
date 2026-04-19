from unittest.mock import MagicMock

import pytest

from claude_almanac.cli import digest as cli_digest


def test_generate_calls_generator(monkeypatch, capsys):
    fake = MagicMock(return_value={
        "digest_path": "/tmp/d.md", "commits_inserted": 2,
        "pruned": 0, "notified": True,
    })
    monkeypatch.setattr("claude_almanac.cli.digest.generator.generate", fake)
    rc = cli_digest.run(["generate", "--date", "2026-04-19"])
    assert rc == 0
    kwargs = fake.call_args.kwargs
    assert kwargs["date"] == "2026-04-19"
    assert kwargs["repo_filter"] is None
    out = capsys.readouterr().out
    assert "/tmp/d.md" in out


def test_generate_respects_repo_and_since(monkeypatch):
    fake = MagicMock(return_value={
        "digest_path": "/tmp/d.md", "commits_inserted": 0,
        "pruned": 0, "notified": None,
    })
    monkeypatch.setattr("claude_almanac.cli.digest.generator.generate", fake)
    cli_digest.run(["generate", "--repo", "r", "--since", "48", "--no-notify"])
    kwargs = fake.call_args.kwargs
    assert kwargs["repo_filter"] == "r"
    assert kwargs["since_hours"] == 48
    assert kwargs["notify"] is False
