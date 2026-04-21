"""Tests for fast-mode Q&A — now routed through the curator factory.

Pre-v0.3.3 this module shelled out directly to `claude -p` and these
tests mocked `subprocess.run`. The migration routes through a curator
instance, so tests now inject a mock curator.
"""
from unittest.mock import MagicMock

from claude_almanac.digest.qa import fast


def test_fast_answer_returns_no_activity_stub(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [],
    )
    out = fast.answer_fast(
        question="what?", digest_markdown="# empty", date="2026-04-19",
        curator=MagicMock(),
    )
    assert "No recent activity" in out


def test_fast_answer_synthesizes_via_curator(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [{
            "repo": "r", "sha": "abcdef1234", "subject": "feat: x",
            "snippet": "feat: x\n\ndiff ...", "distance": 0.1,
        }],
    )
    curator = MagicMock()
    curator.invoke.return_value = "the answer"
    out = fast.answer_fast(
        question="what?", digest_markdown="# ok", date="2026-04-19",
        curator=curator,
    )
    assert out == "the answer"
    curator.invoke.assert_called_once()
    system_prompt, user_turn = curator.invoke.call_args.args
    assert "answer questions about recent repo activity" in system_prompt
    assert "feat: x" in user_turn


def test_fast_raises_when_curator_raises(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [{
            "repo": "r", "sha": "abcdef1234", "subject": "feat: x",
            "snippet": "feat: x\n\ndiff ...", "distance": 0.1,
        }],
    )
    curator = MagicMock()
    curator.invoke.side_effect = RuntimeError("provider blew up")
    import pytest
    with pytest.raises(RuntimeError, match="qa provider error"):
        fast.answer_fast(
            question="x", digest_markdown="y", date="2026-04-19",
            curator=curator,
        )


def test_fast_returns_friendly_message_on_empty_curator_output(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.fast.search_activity",
        lambda **kw: [{
            "repo": "r", "sha": "abcdef1234", "subject": "feat: x",
            "snippet": "feat: x\n\ndiff ...", "distance": 0.1,
        }],
    )
    curator = MagicMock()
    curator.invoke.return_value = ""  # provider returned nothing
    out = fast.answer_fast(
        question="x", digest_markdown="y", date="2026-04-19",
        curator=curator,
    )
    assert "returned no answer" in out


def test_qa_curator_cfg_reuses_narrative_when_qa_unset():
    import dataclasses

    from claude_almanac.core.config import default_config
    from claude_almanac.digest.qa.fast import _qa_curator_cfg

    cfg = default_config()
    cfg = dataclasses.replace(
        cfg,
        digest=dataclasses.replace(
            cfg.digest, narrative_provider="codex", narrative_model="",
        ),
    )
    out = _qa_curator_cfg(cfg)
    assert out.curator.provider == "codex"


def test_qa_curator_cfg_qa_override_wins_over_narrative():
    import dataclasses

    from claude_almanac.core.config import default_config
    from claude_almanac.digest.qa.fast import _qa_curator_cfg

    cfg = default_config()
    cfg = dataclasses.replace(
        cfg,
        digest=dataclasses.replace(
            cfg.digest,
            narrative_provider="codex",
            qa_provider="ollama",
            qa_model="gemma3:4b",
        ),
    )
    out = _qa_curator_cfg(cfg)
    assert out.curator.provider == "ollama"
    assert out.curator.model == "gemma3:4b"


def test_qa_curator_cfg_falls_through_when_everything_unset():
    from claude_almanac.core.config import default_config
    from claude_almanac.digest.qa.fast import _qa_curator_cfg

    cfg = default_config()
    assert _qa_curator_cfg(cfg) is cfg
