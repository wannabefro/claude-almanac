"""Dispatch tests for make_curator."""
from __future__ import annotations

import pytest

from claude_almanac.core.config import Config, CuratorCfg
from claude_almanac.curators import make_curator
from claude_almanac.curators.anthropic_sdk import AnthropicCurator
from claude_almanac.curators.ollama import OllamaCurator


def test_make_curator_returns_ollama_for_ollama_provider() -> None:
    cfg = Config(curator=CuratorCfg(provider="ollama", model="gemma3:4b"))
    c = make_curator(cfg)
    assert isinstance(c, OllamaCurator)
    assert c.model == "gemma3:4b"


def test_make_curator_returns_anthropic_when_key_present(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    cfg = Config(curator=CuratorCfg(
        provider="anthropic_sdk", model="claude-haiku-4-5-20251001",
    ))
    c = make_curator(cfg)
    assert isinstance(c, AnthropicCurator)
    assert c.model == "claude-haiku-4-5-20251001"


def test_make_curator_raises_on_unknown_provider() -> None:
    cfg = Config(curator=CuratorCfg(provider="wat", model="none"))
    with pytest.raises(ValueError, match="unknown curator provider"):
        make_curator(cfg)


def test_make_curator_honors_custom_timeout() -> None:
    cfg = Config(curator=CuratorCfg(provider="ollama", model="gemma3:4b", timeout_s=60))
    c = make_curator(cfg)
    assert c.timeout_s == 60


def test_make_curator_uses_default_timeout_when_zero() -> None:
    cfg = Config(curator=CuratorCfg(provider="ollama", model="gemma3:4b", timeout_s=0))
    c = make_curator(cfg)
    assert c.timeout_s == 30  # Ollama default
