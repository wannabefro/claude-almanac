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


def test_haiku_narrate_falls_back_when_curator_returns_empty():
    curator = MagicMock()
    curator.invoke.return_value = ""
    out = render.haiku_narrate(
        repo="r",
        commits=[{"sha": "abcdef123456", "subject": "feat: x", "author": "t"}],
        curator=curator,
    )
    assert "abcdef12" in out
    assert "feat: x" in out


def test_haiku_narrate_returns_curator_output():
    curator = MagicMock()
    curator.invoke.return_value = "- narrative bullet\n"
    out = render.haiku_narrate(
        repo="r",
        commits=[{"sha": "abcdef123456", "subject": "feat: x", "author": "t"}],
        curator=curator,
    )
    assert out == "- narrative bullet"
    system_prompt, user_turn = curator.invoke.call_args.args
    assert "bullet" in system_prompt.lower()
    assert "feat: x" in user_turn
