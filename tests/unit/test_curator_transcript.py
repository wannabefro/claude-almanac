"""Tests for curator transcript parsing (ported from memory-tools/curator-worker.py)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_almanac.core import curator


def _write_transcript(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events))


def test_iter_turns_yields_user_and_assistant_text(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "hello"}},
            {"message": {"role": "assistant", "content": "hi there"}},
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("user", "hello"), ("assistant", "hi there")]


def test_iter_turns_handles_list_content_with_text_parts(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": [{"type": "text", "text": "q"}]}},
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "a1"},
                        {"type": "tool_use", "name": "Read"},
                        {"type": "text", "text": "a2"},
                    ],
                }
            },
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("user", "q"), ("assistant", "a1\na2")]


def test_iter_turns_skips_tool_result_only_user_turns(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": [{"type": "tool_result", "content": []}]}},
            {"message": {"role": "assistant", "content": "ok"}},
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("assistant", "ok")]


def test_iter_turns_tolerates_malformed_lines(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text('not json\n{"message": {"role": "user", "content": "ok"}}\n')
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("user", "ok")]


def test_parse_full_transcript_concatenates_turns_with_role_tags(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "one"}},
            {"message": {"role": "assistant", "content": "two"}},
        ],
    )
    out = curator._parse_full_transcript(str(p))
    assert "<USER>\none\n</USER>" in out
    assert "<ASSISTANT>\ntwo\n</ASSISTANT>" in out


def test_parse_full_transcript_tail_truncates_when_oversized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curator, "MAX_TRANSCRIPT_CHARS", 100)
    p = tmp_path / "t.jsonl"
    big = "x" * 500
    _write_transcript(p, [{"message": {"role": "user", "content": big}}])
    out = curator._parse_full_transcript(str(p))
    assert len(out) <= 200  # header + truncation margin
    assert out.startswith("...(earlier turns truncated)")


def test_read_conversation_tail_prefers_env_var_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "t.jsonl"
    _write_transcript(p, [{"message": {"role": "user", "content": "env path"}}])
    monkeypatch.setenv("CLAUDE_ALMANAC_TRANSCRIPT", str(p))
    out = curator._read_conversation_tail()
    assert "<USER>\nenv path\n</USER>" in out


def test_read_conversation_tail_returns_empty_when_no_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_ALMANAC_TRANSCRIPT", raising=False)
    assert curator._read_conversation_tail() == ""


def test_tool_use_messages_preserve_surrounding_text(tmp_path: Path) -> None:
    """Assistant turn with text + tool_use + text: text parts joined, tool_use skipped."""
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "find foo"}},
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Let me search."},
                        {"type": "tool_use", "name": "Grep", "input": {"q": "foo"}},
                        {"type": "text", "text": "Found it in bar.py."},
                    ],
                }
            },
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [
        ("user", "find foo"),
        ("assistant", "Let me search.\nFound it in bar.py."),
    ]


def test_multi_part_content_does_not_collapse_to_first_block(tmp_path: Path) -> None:
    """Thinking + text + tool_use interleaved: text surfaces, thinking skipped."""
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "internal"},
                        {"type": "text", "text": "a"},
                        {"type": "tool_use", "name": "Read"},
                        {"type": "text", "text": "b"},
                    ],
                }
            },
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("assistant", "a\nb")]


def test_compaction_event_yields_boundary_turn(tmp_path: Path) -> None:
    """{\"type\": \"summary\", ...} surfaces as a ('compaction', summary) turn."""
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "hi"}},
            {"type": "summary", "summary": "earlier discussion about foo"},
            {"message": {"role": "assistant", "content": "ok"}},
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    kinds = [t[0] for t in turns]
    assert "compaction" in kinds
    compaction_text = next(t[1] for t in turns if t[0] == "compaction")
    assert "earlier discussion about foo" in compaction_text


def test_interrupted_turn_yields_empty_assistant(tmp_path: Path) -> None:
    """User turn with no following assistant: parser must not raise."""
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "cut short"}},
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert turns == [("user", "cut short")]


def test_subagent_stop_surfaces_as_own_turn_type(tmp_path: Path) -> None:
    """SubagentStop markers become ('subagent_stop', ...) turns, not merged."""
    p = tmp_path / "t.jsonl"
    _write_transcript(
        p,
        [
            {"message": {"role": "user", "content": "spawn something"}},
            {"type": "subagent_stop", "summary": "explore agent finished"},
            {"message": {"role": "assistant", "content": "done"}},
        ],
    )
    turns = list(curator._iter_turns(str(p)))
    assert ("subagent_stop", "explore agent finished") in turns
    assert ("assistant", "done") in turns
