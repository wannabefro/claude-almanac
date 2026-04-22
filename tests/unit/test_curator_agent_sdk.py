"""ClaudeAgentSdkCurator contract tests.

Mocks the agent SDK's ``query()`` so we never spawn the Claude CLI
subprocess or hit the live Anthropic API.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def test_curator_returns_text_from_assistant_message(monkeypatch) -> None:
    from claude_almanac.curators import agent_sdk as mod

    # Build fake AssistantMessage-with-TextBlock mimicking the SDK shape.
    fake_block = MagicMock(spec=mod.TextBlock)
    fake_block.text = '{"hits":[]}'
    fake_am = MagicMock(spec=mod.AssistantMessage)
    fake_am.content = [fake_block]

    async def fake_query(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield fake_am

    monkeypatch.setattr(mod, "query", fake_query)

    c = mod.ClaudeAgentSdkCurator(model="claude-haiku-4-5-20251001", timeout_s=60.0)
    out = c.invoke("sys", "user")
    assert out == '{"hits":[]}'


def test_curator_swallows_exceptions_returns_empty(monkeypatch, caplog) -> None:
    from claude_almanac.curators import agent_sdk as mod

    async def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("sdk is broken")
        yield  # pragma: no cover — make it a generator for type shape

    monkeypatch.setattr(mod, "query", boom)

    c = mod.ClaudeAgentSdkCurator(model="claude-haiku-4-5-20251001")
    caplog.set_level("WARNING")
    assert c.invoke("sys", "user") == ""
    assert "agent_sdk" in caplog.text.lower()


def test_factory_dispatches_claude_agent_sdk() -> None:
    from claude_almanac.core.config import Config, CuratorCfg
    from claude_almanac.curators.factory import make_curator

    cfg = Config()
    cfg.curator = CuratorCfg(
        provider="claude_agent_sdk",
        model="claude-haiku-4-5-20251001",
        timeout_s=90,
    )
    curator = make_curator(cfg)
    assert curator.__class__.__name__ == "ClaudeAgentSdkCurator"
    assert curator.model == "claude-haiku-4-5-20251001"
    assert curator.timeout_s == 90


def test_factory_uses_default_timeout_for_agent_sdk_when_zero() -> None:
    from claude_almanac.core.config import Config, CuratorCfg
    from claude_almanac.curators.factory import make_curator

    cfg = Config()
    cfg.curator = CuratorCfg(
        provider="claude_agent_sdk",
        model="claude-haiku-4-5-20251001",
        timeout_s=0,
    )
    curator = make_curator(cfg)
    assert curator.timeout_s == 120  # claude_agent_sdk default
