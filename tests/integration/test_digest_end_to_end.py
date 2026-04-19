"""End-to-end: fresh install dir -> generator -> server serves the digest.

Marked integration because it spins up an in-process TestClient + writes
real files; skipped by default because it calls `git` and assumes the
claude-almanac Ollama+claude-CLI stack isn't needed (embedder is mocked).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


def test_generate_then_serve_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "data" / "digests").mkdir(parents=True)
    (tmp_path / "data" / "global").mkdir(parents=True)
    (tmp_path / "data" / "projects").mkdir(parents=True)

    # Real git repo with one commit.
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "file.txt").write_text("hi\n")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: start"], cwd=repo, check=True, capture_output=True)

    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path=str(repo), alias="r")]

    emb = MagicMock()
    emb.name = "ollama"
    emb.dim = 4
    emb.distance = "l2"
    emb.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]

    from claude_almanac.digest import generator
    monkeypatch.setattr(
        "claude_almanac.digest.generator.make_embedder",
        lambda *a, **kw: emb,
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.haiku_narrate",
        lambda **kw: "- committed stuff",
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.digest_notify.notify",
        lambda **kw: False,
    )
    result = generator.generate(cfg=cfg, date="2026-04-19", notify=False)
    assert Path(result["digest_path"]).exists()

    import importlib
    import claude_almanac.digest.server as server_mod
    importlib.reload(server_mod)
    client = TestClient(server_mod.app)
    r = client.get("/digest/2026-04-19")
    assert r.status_code == 200
    assert "committed stuff" in r.text or "feat: start" in r.text
