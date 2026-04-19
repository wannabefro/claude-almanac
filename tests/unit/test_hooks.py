import io
import json

from claude_almanac.hooks import curate as hooks_curate
from claude_almanac.hooks import retrieve as hooks_retrieve


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
    def fake_spawn(transcript_path=None):
        called["spawned"] = True
        called["transcript_path"] = transcript_path
    monkeypatch.setattr("claude_almanac.hooks.curate._spawn_worker", fake_spawn)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    hooks_curate.main()
    assert called["spawned"] is True


def test_curate_hook_passes_transcript_path_via_env(monkeypatch):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})

        class P:
            pass

        return P()

    monkeypatch.setattr(hooks_curate.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"transcript_path": "/tmp/example.jsonl"}))
    )
    hooks_curate.main()
    assert captured["env"].get("CLAUDE_ALMANAC_HOOK_TRANSCRIPT") == "/tmp/example.jsonl"
