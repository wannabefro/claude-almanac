"""Unit tests for the curator worker."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from claude_almanac.core import curator


def test_main_loads_config_and_invokes_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"message": {"role": "user", "content": "hi"}}),
                json.dumps({"message": {"role": "assistant", "content": "hello"}}),
            ]
        )
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_TRANSCRIPT", str(transcript))

    called = {"ran": False}
    monkeypatch.setattr(
        "claude_almanac.core.curator._run_llm",
        lambda *a, **kw: '{"decisions": [{"action": "archive_turn", "text": "x"}]}',
    )
    monkeypatch.setattr(
        "claude_almanac.core.curator._apply_decisions",
        lambda *a, **kw: called.update(ran=True),
    )
    curator.main()
    assert called["ran"] is True


def test_apply_decisions_redirects_on_dup(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    # stub dedup to always redirect
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: ("existing.md", 14.0),
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry", lambda *a, **kw: 1
    )
    decisions = [
        {
            "action": "write_md",
            "scope": "global",
            "slug": "new.md",
            "kind": "project",
            "text": "body",
        }
    ]
    from claude_almanac.core import paths as p

    p.ensure_dirs()
    curator._apply_decisions(decisions)
    # File should be written under the redirected slug, not the original
    assert (p.global_memory_dir() / "existing.md").exists()
    assert not (p.global_memory_dir() / "new.md").exists()
