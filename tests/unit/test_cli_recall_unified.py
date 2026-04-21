"""Tests for v0.3.6 unified recall: `search` blends memories + code-index.

`search` now includes both, `memories` is memory-only, `code` stays code-only.
"""
from __future__ import annotations

from unittest.mock import patch

from claude_almanac.cli import recall


def test_search_unified_prints_memory_section_when_code_index_absent(
    tmp_path, monkeypatch, capsys,
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    # No content-index.db exists → code block is empty; only memory section prints.
    with (
        patch.object(recall, "_collect_memory_hits", return_value=[]),
        patch.object(recall, "_collect_code_block", return_value=""),
        patch("claude_almanac.cli.recall.make_embedder") as mk,
    ):
        mk.return_value.embed.return_value = [[0.1] * 1024]
        recall._search_unified("what is l10n", all_projects=False)
    out = capsys.readouterr().out
    assert "no matches" in out.lower()


def test_search_unified_includes_code_block_when_present(
    tmp_path, monkeypatch, capsys,
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    fake_code_block = "## Relevant code\n### Symbols\n- [sym] x.py:1-5  foo"
    with (
        patch.object(recall, "_collect_memory_hits", return_value=[]),
        patch.object(recall, "_collect_code_block", return_value=fake_code_block),
        patch("claude_almanac.cli.recall.make_embedder") as mk,
    ):
        mk.return_value.embed.return_value = [[0.1] * 1024]
        recall._search_unified("foo", all_projects=False)
    out = capsys.readouterr().out
    assert "Relevant code" in out
    assert "foo" in out


def test_search_memories_never_prints_code_block(tmp_path, monkeypatch, capsys):
    """Memory-only path must not invoke code-index even when one exists."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    called = {"code": 0}
    def _track_code(*a, **kw):
        called["code"] += 1
        return "## Relevant code\n### Symbols\n- [sym] x"
    with (
        patch.object(recall, "_collect_memory_hits", return_value=[]),
        patch.object(recall, "_collect_code_block", side_effect=_track_code),
        patch("claude_almanac.cli.recall.make_embedder") as mk,
    ):
        mk.return_value.embed.return_value = [[0.1] * 1024]
        recall._search_memories("x", all_projects=False)
    assert called["code"] == 0
    out = capsys.readouterr().out
    assert "Relevant code" not in out


def test_run_dispatch_search_goes_to_unified():
    with patch.object(recall, "_search_unified") as unified:
        recall.run(["search", "hello"])
    unified.assert_called_once()
    _, kwargs = unified.call_args
    assert kwargs["all_projects"] is False


def test_run_dispatch_memories_goes_to_memory_only():
    with patch.object(recall, "_search_memories") as mem:
        recall.run(["memories", "hello"])
    mem.assert_called_once()
    _, kwargs = mem.call_args
    assert kwargs["all_projects"] is False


def test_run_dispatch_memories_all():
    with patch.object(recall, "_search_memories") as mem:
        recall.run(["memories-all", "x"])
    mem.assert_called_once()
    _, kwargs = mem.call_args
    assert kwargs["all_projects"] is True


def test_collect_code_block_returns_empty_when_no_index(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    assert recall._collect_code_block([0.1] * 1024) == ""
