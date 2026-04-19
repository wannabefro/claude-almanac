import json
import io
from unittest.mock import patch
from claude_almanac.hooks import retrieve as hooks_retrieve
from claude_almanac.hooks import curate as hooks_curate


def test_retrieve_hook_reads_stdin_prints_context(monkeypatch, capsys):
    payload = {"prompt": "what did we decide about X?"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr("claude_almanac.hooks.retrieve.core_retrieve.run",
                        lambda prompt: "## Relevant memories\n- [project] md:x.md\n")
    hooks_retrieve.main()
    captured = capsys.readouterr()
    assert "Relevant memories" in captured.out


def test_retrieve_hook_no_prompt_prints_nothing(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setattr("claude_almanac.hooks.retrieve.core_retrieve.run",
                        lambda prompt: "")
    hooks_retrieve.main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_curate_hook_forks_worker_and_exits(monkeypatch):
    called = {}
    def fake_spawn():
        called["spawned"] = True
    monkeypatch.setattr("claude_almanac.hooks.curate._spawn_worker", fake_spawn)
    hooks_curate.main()
    assert called["spawned"] is True
