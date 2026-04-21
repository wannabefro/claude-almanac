import json

from claude_almanac.rollups.triggers import parse_hook_event


def test_parse_session_end_event():
    payload = json.dumps({
        "hook_event_name": "SessionEnd",
        "transcript_path": "/tmp/foo.jsonl",
        "session_id": "abc",
        "cwd": "/home/user/proj",
    })
    ev = parse_hook_event(payload)
    assert ev is not None
    assert ev.trigger == "session_end"
    assert ev.session_id == "abc"
    assert str(ev.transcript_path) == "/tmp/foo.jsonl"


def test_parse_pre_compact_event():
    payload = json.dumps({
        "hook_event_name": "PreCompact",
        "transcript_path": "/tmp/x.jsonl",
        "session_id": "xyz",
        "cwd": "/home/user/proj",
    })
    ev = parse_hook_event(payload)
    assert ev is not None
    assert ev.trigger == "pre_compact"


def test_parse_unknown_event_returns_none():
    payload = json.dumps({"hook_event_name": "Stop", "session_id": "x",
                          "transcript_path": "/t", "cwd": "/c"})
    assert parse_hook_event(payload) is None


def test_parse_missing_fields_returns_none():
    payload = json.dumps({"hook_event_name": "SessionEnd"})
    assert parse_hook_event(payload) is None


def test_parse_malformed_json_returns_none():
    assert parse_hook_event("not json") is None
