"""AnthropicCurator unit tests. Mock the anthropic client."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

from claude_almanac.curators.anthropic_sdk import AnthropicCurator


def test_invoke_passes_system_and_user_and_returns_text(monkeypatch) -> None:
    fake_response = SimpleNamespace(content=[SimpleNamespace(text='{"decisions": []}')])
    mock_messages = MagicMock()
    mock_messages.create.return_value = fake_response
    mock_client = SimpleNamespace(messages=mock_messages)

    created = {}

    def _fake_anthropic(*, api_key: str | None = None) -> object:
        created["api_key"] = api_key
        return mock_client

    monkeypatch.setattr(
        "claude_almanac.curators.anthropic_sdk.anthropic.Anthropic",
        _fake_anthropic,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    c = AnthropicCurator(model="claude-haiku-4-5-20251001", timeout_s=10)
    out = c.invoke("SYSTEM", "USER TAIL")

    assert out == '{"decisions": []}'
    mock_messages.create.assert_called_once()
    kwargs = mock_messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["system"] == "SYSTEM"
    assert kwargs["messages"] == [{"role": "user", "content": "USER TAIL"}]
    assert kwargs["max_tokens"] == 2048
    assert kwargs["temperature"] == 0
    assert kwargs["timeout"] == 10


def test_invoke_returns_empty_on_api_error(monkeypatch, caplog) -> None:
    mock_messages = MagicMock()
    # Any anthropic.APIError subclass reaches the impl's except clause.
    # APIConnectionError is the canonical "network layer failure" case.
    mock_messages.create.side_effect = anthropic.APIConnectionError(
        request=MagicMock()
    )
    mock_client = SimpleNamespace(messages=mock_messages)
    monkeypatch.setattr(
        "claude_almanac.curators.anthropic_sdk.anthropic.Anthropic",
        lambda *a, **kw: mock_client,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    c = AnthropicCurator(model="claude-haiku-4-5-20251001", timeout_s=5)
    caplog.set_level("WARNING")
    out = c.invoke("s", "u")
    assert out == ""
    assert "anthropic" in caplog.text.lower()


def test_missing_api_key_raises_on_instantiation(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        AnthropicCurator(model="claude-haiku-4-5-20251001", timeout_s=5)
