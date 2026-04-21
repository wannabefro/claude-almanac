"""Regression tests for _recover_unescaped_quotes + the parse-retry path.

v0.3.10 adds a tolerant parser that auto-escapes inner `"` when gemma
(or any other provider not on Ollama's schema-constrained path) emits
malformed JSON like:

    {"content": "He said "hi" today"}

The Ollama grammar constraint now handles most cases at token-gen, but
this recovery path is belt-and-braces for anthropic_sdk / claude_cli /
codex outputs that slip through.
"""
from __future__ import annotations

import logging

from claude_almanac.core.curator import _parse_decisions, _recover_unescaped_quotes


def test_recover_fixes_unescaped_inner_quote():
    raw = '{"decisions":[{"content":"He said "hi" today"}]}'
    recovered = _recover_unescaped_quotes(raw)
    assert recovered is not None
    # Should round-trip through json.loads now.
    import json
    parsed = json.loads(recovered)
    assert parsed["decisions"][0]["content"] == 'He said "hi" today'


def test_recover_preserves_escaped_quotes():
    raw = r'{"decisions":[{"content":"He said \"hi\" today"}]}'
    # Input is already valid — recovery returns None (no changes).
    recovered = _recover_unescaped_quotes(raw)
    assert recovered is None


def test_recover_preserves_structural_quotes():
    raw = '{"decisions":[{"action":"write_md","body":"content"}]}'
    # Already valid JSON, no inner quotes to escape.
    assert _recover_unescaped_quotes(raw) is None


def test_recover_returns_none_on_unbalanced_string():
    # Unterminated string — don't pretend to repair.
    raw = '{"decisions":[{"content":"unterminated'
    assert _recover_unescaped_quotes(raw) is None


def test_recover_handles_gemma_failure_mode():
    """The exact failure mode from logs: adopted a "Engineer's Ops Console" aesthetic."""
    raw = (
        '{"decisions":[{"action":"update_md","content":'
        '"The TUI adopted a "Engineer\'s Ops Console" aesthetic using shared styles."}]}'
    )
    recovered = _recover_unescaped_quotes(raw)
    assert recovered is not None
    import json
    parsed = json.loads(recovered)
    assert parsed["decisions"][0]["action"] == "update_md"
    assert "Engineer" in parsed["decisions"][0]["content"]


def test_parse_decisions_retries_with_recovery(caplog):
    """_parse_decisions uses _recover_unescaped_quotes on the first JSON failure."""
    raw = '{"decisions":[{"action":"skip_all","reason":"hit a "snag" in parsing"}]}'
    with caplog.at_level(logging.INFO, logger="claude_almanac.core.curator"):
        decisions = _parse_decisions(raw)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "skip_all"
    # Info log confirms the recovery path fired.
    assert any("recovered" in r.getMessage().lower() for r in caplog.records)


def test_parse_decisions_returns_empty_when_recovery_also_fails(caplog):
    """Completely malformed input still yields [] + warning (no silent success)."""
    raw = "this is not JSON at all and has no repairable structure"
    with caplog.at_level(logging.WARNING, logger="claude_almanac.core.curator"):
        decisions = _parse_decisions(raw)
    assert decisions == []
    # Warning is the final non-JSON log — recovery didn't help.
    assert any("non-JSON" in r.getMessage() for r in caplog.records)
