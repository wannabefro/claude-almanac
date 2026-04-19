from unittest.mock import MagicMock

import pytest

from claude_almanac.digest.qa import api


def test_fast_routes_to_answer_fast(monkeypatch):
    monkeypatch.setattr(
        "claude_almanac.digest.qa.api.answer_fast",
        lambda **kw: "FAST",
    )
    out = api.answer_question(
        question="q", digest_markdown="d", date="2026-04-19", mode="fast",
    )
    assert out == "FAST"


def test_deep_routes_to_answer_deep(monkeypatch):
    class R:
        answer = "DEEP"
    monkeypatch.setattr(
        "claude_almanac.digest.qa.api.answer_deep",
        lambda **kw: R(),
    )
    out = api.answer_question(
        question="q", digest_markdown="d", date="2026-04-19", mode="deep",
    )
    assert out == "DEEP"


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        api.answer_question(
            question="q", digest_markdown="d", date="2026-04-19",
            mode="other",  # type: ignore[arg-type]
        )
