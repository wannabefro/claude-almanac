"""Tests for the digest narrator routing through the curator factory."""
from __future__ import annotations

from unittest.mock import MagicMock

from claude_almanac.digest.render import haiku_narrate


def _commits(n: int = 2) -> list[dict]:
    return [
        {"sha": f"abc{i:04d}de", "subject": f"change {i}", "author": "dev"}
        for i in range(n)
    ]


def test_haiku_narrate_passes_prompt_and_returns_curator_output():
    curator = MagicMock()
    curator.invoke.return_value = "- semantic bullet 1\n- semantic bullet 2"
    out = haiku_narrate(repo="x", commits=_commits(3), curator=curator)
    assert out == "- semantic bullet 1\n- semantic bullet 2"
    curator.invoke.assert_called_once()
    system_prompt, user_turn = curator.invoke.call_args.args
    assert "2-3 markdown bullet" in system_prompt
    assert "Repository: x" in user_turn
    assert "change 0" in user_turn
    assert "change 1" in user_turn


def test_haiku_narrate_empty_commits_returns_sentinel():
    curator = MagicMock()
    out = haiku_narrate(repo="x", commits=[], curator=curator)
    assert out == "_no commits in window_"
    curator.invoke.assert_not_called()


def test_haiku_narrate_falls_back_when_curator_returns_empty():
    curator = MagicMock()
    curator.invoke.return_value = ""
    out = haiku_narrate(repo="x", commits=_commits(2), curator=curator)
    assert "abc0000d" in out  # bare sha prefix fallback
    assert "change 0" in out
    assert "change 1" in out


def test_haiku_narrate_falls_back_when_curator_raises():
    curator = MagicMock()
    curator.invoke.side_effect = RuntimeError("simulated curator failure")
    out = haiku_narrate(repo="x", commits=_commits(1), curator=curator)
    assert "abc0000d" in out


def test_digest_cfg_narrative_overrides_parse():
    from claude_almanac.core.config import load_config_from_text

    text = """
curator:
  provider: ollama
  model: gemma4:e4b
digest:
  narrative_provider: codex
  narrative_model: ""
"""
    cfg = load_config_from_text(text)
    assert cfg.digest.narrative_provider == "codex"
    assert cfg.digest.narrative_model == ""
    assert cfg.curator.provider == "ollama"  # unchanged


def test_digest_curator_cfg_no_override_returns_cfg_unchanged():
    from claude_almanac.core.config import default_config
    from claude_almanac.digest.generator import _digest_curator_cfg

    cfg = default_config()
    assert _digest_curator_cfg(cfg) is cfg


def test_digest_curator_cfg_applies_overrides():
    import dataclasses

    from claude_almanac.core.config import default_config
    from claude_almanac.digest.generator import _digest_curator_cfg

    cfg = default_config()
    cfg = dataclasses.replace(
        cfg,
        digest=dataclasses.replace(
            cfg.digest, narrative_provider="codex", narrative_model="",
        ),
    )
    out = _digest_curator_cfg(cfg)
    assert out.curator.provider == "codex"
    # Original cfg is untouched (immutable semantics via dataclasses.replace)
    assert cfg.curator.provider == default_config().curator.provider
