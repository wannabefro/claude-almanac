"""Fixture-parity suite: each curator provider must produce valid
decisions for the same set of transcripts. Guards against silent
regressions (shape drift, chatty drift, missing durable-memory emission).

Runs both OllamaCurator (via live gemma3:4b) and AnthropicCurator
(via live ANTHROPIC_API_KEY, when present) against real-session
transcripts under ``tests/fixtures/transcripts/``.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from claude_almanac.core.config import Config, CuratorCfg
from claude_almanac.core.curator import (
    _build_system_prompt,
    _parse_decisions,
    _parse_full_transcript,
)
from claude_almanac.curators import make_curator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "transcripts"
ALL_FIXTURES = [
    "chatty_output",
    "pure_chatter",
    "durable_memory_signal",
    "large_180kb",
]
_VALID_ACTIONS = {"write_md", "update_md", "insert_archive", "archive_turn", "skip_all"}


def _invoke(provider_cfg: CuratorCfg, tail: str) -> list[dict]:
    cfg = Config(curator=provider_cfg)
    curator = make_curator(cfg)
    raw = curator.invoke(_build_system_prompt(), tail)
    return _parse_decisions(raw)


@pytest.fixture
def ollama_cfg() -> CuratorCfg:
    return CuratorCfg(provider="ollama", model="gemma3:4b", timeout_s=45)


@pytest.fixture
def anthropic_cfg() -> CuratorCfg:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; skipping anthropic provider tests")
    return CuratorCfg(
        provider="anthropic_sdk",
        model="claude-haiku-4-5-20251001",
        timeout_s=20,
    )


def _assert_valid_shape(decisions: list[dict]) -> None:
    assert isinstance(decisions, list)
    for d in decisions:
        assert d.get("action") in _VALID_ACTIONS, f"bad action: {d!r}"
        if d.get("action") in ("write_md", "update_md"):
            assert d.get("name") or d.get("slug"), f"missing name: {d!r}"
            assert d.get("content") or d.get("text"), f"missing content: {d!r}"


@pytest.mark.integration
@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_ollama_produces_valid_shape(ollama_cfg: CuratorCfg, fixture_name: str) -> None:
    tail = _parse_full_transcript(str(FIXTURES / f"{fixture_name}.jsonl"))
    decisions = _invoke(ollama_cfg, tail)
    _assert_valid_shape(decisions)


@pytest.mark.integration
@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_anthropic_produces_valid_shape(
    anthropic_cfg: CuratorCfg, fixture_name: str,
) -> None:
    tail = _parse_full_transcript(str(FIXTURES / f"{fixture_name}.jsonl"))
    decisions = _invoke(anthropic_cfg, tail)
    _assert_valid_shape(decisions)


@pytest.mark.integration
def test_ollama_emits_durable_memory_on_signal_fixture(ollama_cfg: CuratorCfg) -> None:
    tail = _parse_full_transcript(str(FIXTURES / "durable_memory_signal.jsonl"))
    decisions = _invoke(ollama_cfg, tail)
    non_skip = [d for d in decisions if d.get("action") != "skip_all"]
    assert non_skip, (
        "ollama/gemma3:4b dropped a clear durable-memory signal — "
        "curator silent-drop regression"
    )


@pytest.mark.integration
def test_anthropic_emits_durable_memory_on_signal_fixture(
    anthropic_cfg: CuratorCfg,
) -> None:
    tail = _parse_full_transcript(str(FIXTURES / "durable_memory_signal.jsonl"))
    decisions = _invoke(anthropic_cfg, tail)
    non_skip = [d for d in decisions if d.get("action") != "skip_all"]
    assert non_skip, "anthropic/Haiku dropped a clear durable-memory signal"


@pytest.mark.integration
def test_ollama_does_not_invent_memories_from_pure_chatter(
    ollama_cfg: CuratorCfg,
) -> None:
    tail = _parse_full_transcript(str(FIXTURES / "pure_chatter.jsonl"))
    decisions = _invoke(ollama_cfg, tail)
    writes = [d for d in decisions if d.get("action") in ("write_md", "update_md")]
    assert not writes, f"ollama hallucinated memories from chatter: {writes!r}"


@pytest.mark.integration
def test_anthropic_does_not_invent_memories_from_pure_chatter(
    anthropic_cfg: CuratorCfg,
) -> None:
    tail = _parse_full_transcript(str(FIXTURES / "pure_chatter.jsonl"))
    decisions = _invoke(anthropic_cfg, tail)
    writes = [d for d in decisions if d.get("action") in ("write_md", "update_md")]
    assert not writes, f"anthropic hallucinated memories from chatter: {writes!r}"
