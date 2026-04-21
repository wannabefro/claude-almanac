import json
from unittest.mock import patch

from claude_almanac.hooks.rollup import run_hook


def test_run_hook_dispatches_on_valid_session_end(tmp_path):
    transcript = tmp_path / "s.jsonl"
    transcript.write_text('{"type":"user","message":{"content":"hi"}}\n' * 5)
    payload = json.dumps({
        "hook_event_name": "SessionEnd",
        "transcript_path": str(transcript),
        "session_id": "abc",
        "cwd": str(tmp_path),
    })
    with patch("claude_almanac.hooks.rollup._spawn_background") as spawn:
        run_hook(payload)
        assert spawn.call_count == 1
        ev = spawn.call_args.args[0]
        assert ev.trigger == "session_end"


def test_run_hook_noops_on_malformed_json():
    with patch("claude_almanac.hooks.rollup._spawn_background") as spawn:
        run_hook("not json")
        assert spawn.call_count == 0


def test_run_hook_noops_on_unknown_event():
    payload = json.dumps({
        "hook_event_name": "Stop",
        "transcript_path": "/t", "session_id": "x", "cwd": "/c",
    })
    with patch("claude_almanac.hooks.rollup._spawn_background") as spawn:
        run_hook(payload)
        assert spawn.call_count == 0


def test_run_hook_noops_when_rollup_disabled(monkeypatch, tmp_path):
    # If cfg.rollup.enabled is False, the hook should not spawn.
    payload = json.dumps({
        "hook_event_name": "SessionEnd",
        "transcript_path": str(tmp_path / "s.jsonl"),
        "session_id": "abc",
        "cwd": str(tmp_path),
    })
    (tmp_path / "s.jsonl").write_text("{}")

    # Patch load_config to return a config with rollup.enabled=False
    import dataclasses

    from claude_almanac.core.config import load_config_from_text

    def _cfg_disabled():
        cfg = load_config_from_text("")
        return dataclasses.replace(cfg, rollup=dataclasses.replace(cfg.rollup, enabled=False))

    with patch("claude_almanac.hooks.rollup.load_config", _cfg_disabled), \
         patch("claude_almanac.hooks.rollup._spawn_background") as spawn:
        run_hook(payload)
        assert spawn.call_count == 0
