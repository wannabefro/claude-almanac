from unittest.mock import MagicMock

from claude_almanac.digest import render


def test_render_digest_includes_all_sections():
    inputs = render.DigestInputs(
        date="2026-04-19",
        window_hours=24,
        new_memories=[{"scope": "global", "slug": "x",
                       "kind": "project", "name": "X", "description": "d"}],
        retrievals={"md:a.md": 3},
        commits_by_repo={"r": [{"sha": "abcdef123456", "subject": "feat: x", "author": "t"}]},
        narratives_by_repo={"r": "- did things"},
    )
    out = render.render_digest(inputs)
    assert "# Daily digest — 2026-04-19" in out
    assert "## New memories" in out
    assert "`x`" in out
    assert "## Frequently surfaced" in out
    assert "md:a.md" in out
    assert "### r" in out
    assert "- did things" in out
    assert "## Totals" in out


def test_render_digest_handles_empty_sections():
    inputs = render.DigestInputs(
        date="2026-04-19", window_hours=24, new_memories=[],
        retrievals={}, commits_by_repo={}, narratives_by_repo={},
    )
    out = render.render_digest(inputs)
    assert "_no new memories_" in out
    assert "_no retrievals recorded in window_" in out
    assert "_no activity_" in out


def test_haiku_narrate_falls_back_on_cli_failure(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("claude: not found")
    monkeypatch.setattr("subprocess.run", boom)
    out = render.haiku_narrate(
        repo="r",
        commits=[{"sha": "abcdef123456", "subject": "feat: x", "author": "t"}],
        model="haiku",
    )
    assert "abcdef12" in out
    assert "feat: x" in out


def test_haiku_narrate_uses_claude_cli(monkeypatch):
    captured = {}
    def fake_run(argv, input, capture_output, text, timeout, check):
        captured["argv"] = argv
        captured["stdin"] = input
        m = MagicMock()
        m.returncode = 0
        m.stdout = "- narrative bullet\n"
        m.stderr = ""
        return m
    monkeypatch.setattr("subprocess.run", fake_run)
    out = render.haiku_narrate(
        repo="r",
        commits=[{"sha": "abcdef123456", "subject": "feat: x", "author": "t"}],
        model="haiku",
    )
    assert out == "- narrative bullet"
    assert captured["argv"] == ["claude", "-p", "--model", "haiku"]
    assert "feat: x" in captured["stdin"]
