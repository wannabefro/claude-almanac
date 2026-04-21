import json
from pathlib import Path

from claude_almanac.rollups.transcript import read_windowed_transcript


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(item) for item in lines) + "\n")


def test_missing_file_returns_empty(tmp_path):
    out = read_windowed_transcript(tmp_path / "nope.jsonl", max_tokens=1000)
    assert out.turns == []
    assert out.turn_count == 0
    assert out.rendered == ""


def test_reads_all_turns_when_under_budget(tmp_path):
    p = tmp_path / "s.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": "hello"}},
        {"type": "assistant", "message": {"content": "hi"}},
    ])
    out = read_windowed_transcript(p, max_tokens=1000)
    assert out.turn_count == 2
    assert "hello" in out.rendered
    assert "hi" in out.rendered


def test_keeps_session_tail_when_over_budget(tmp_path):
    p = tmp_path / "s.jsonl"
    turns = [{"type": "user", "message": {"content": f"msg-{i}"}} for i in range(100)]
    _write_jsonl(p, turns)
    out = read_windowed_transcript(p, max_tokens=100)  # forces truncation
    # Last message must be kept; earliest dropped.
    assert "msg-99" in out.rendered
    assert "msg-0" not in out.rendered
    assert out.turn_count <= 100


def test_tool_result_over_4k_is_shimmed(tmp_path):
    p = tmp_path / "s.jsonl"
    big = "x" * 5000
    _write_jsonl(p, [
        {"type": "tool_result", "tool_use_id": "T1", "tool_name": "Read", "content": big},
    ])
    out = read_windowed_transcript(p, max_tokens=10000)
    assert big not in out.rendered
    assert "[tool-result:" in out.rendered
    assert "Read" in out.rendered


def test_small_tool_result_is_kept_verbatim(tmp_path):
    p = tmp_path / "s.jsonl"
    small = "small output"
    _write_jsonl(p, [
        {"type": "tool_result", "tool_use_id": "T1", "tool_name": "Read", "content": small},
    ])
    out = read_windowed_transcript(p, max_tokens=10000)
    assert small in out.rendered


def test_malformed_json_line_skipped(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(
        json.dumps({"type": "user", "message": {"content": "valid"}}) + "\n"
        + "not valid json\n"
        + json.dumps({"type": "assistant", "message": {"content": "also valid"}}) + "\n"
    )
    out = read_windowed_transcript(p, max_tokens=10000)
    assert out.turn_count == 2  # malformed line silently skipped
    assert "valid" in out.rendered
    assert "also valid" in out.rendered


def test_message_content_as_list_of_text_blocks(tmp_path):
    # Some Claude Code transcript shapes use content as a list of blocks,
    # e.g. [{"type": "text", "text": "hello"}].
    p = tmp_path / "s.jsonl"
    _write_jsonl(p, [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "blocky"}]}},
    ])
    out = read_windowed_transcript(p, max_tokens=10000)
    assert "blocky" in out.rendered
