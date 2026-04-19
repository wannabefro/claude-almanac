import asyncio
from unittest.mock import MagicMock, AsyncMock

import pytest

from claude_almanac.digest.qa import deep


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeToolUseBlock:
    pass


class _FakeAssistantMessage:
    def __init__(self, blocks: list) -> None:
        self.content = blocks


@pytest.fixture
def fake_sdk(monkeypatch):
    calls = {"options": None}

    def fake_create_server(**kw):
        return MagicMock(name="server")

    async def fake_query(prompt, options):
        calls["options"] = options
        calls["prompt"] = prompt
        yield _FakeAssistantMessage([_FakeTextBlock("hello answer")])

    def fake_tool(name, desc, schema):
        def _dec(fn):
            return fn
        return _dec

    monkeypatch.setattr(deep, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(deep, "TextBlock", _FakeTextBlock)
    monkeypatch.setattr(deep, "ToolUseBlock", _FakeToolUseBlock)
    monkeypatch.setattr(deep, "create_sdk_mcp_server", fake_create_server)
    monkeypatch.setattr(deep, "query", fake_query)
    monkeypatch.setattr(deep, "sdk_tool", fake_tool)
    # Ensure ClaudeAgentOptions exists as a plain passthrough
    monkeypatch.setattr(deep, "ClaudeAgentOptions", lambda **kw: kw)
    return calls


def test_answer_deep_returns_text(fake_sdk):
    result = deep.answer_deep(
        question="what?", digest_markdown="# d", date="2026-04-19",
        max_iterations=2, wall_clock_s=5.0,
    )
    assert result.answer == "hello answer"
    assert result.truncated is False
    assert result.tool_calls == 0


def test_answer_deep_marks_truncated_on_cap(monkeypatch, fake_sdk):
    async def fake_query_many(prompt, options):
        for _ in range(3):
            yield _FakeAssistantMessage([_FakeToolUseBlock()])
        yield _FakeAssistantMessage([_FakeTextBlock("partial")])
    monkeypatch.setattr(deep, "query", fake_query_many)
    result = deep.answer_deep(
        question="q", digest_markdown="d", date="2026-04-19",
        max_iterations=2, wall_clock_s=5.0,
    )
    assert result.truncated is True
    assert "truncated" in result.answer
