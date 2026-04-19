from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_almanac.digest.qa import registry
from claude_almanac.digest.qa.tools import search_activity, git_show


def test_search_activity_empty_db_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    out = search_activity.search_activity(query="anything")
    assert out == []


def test_search_activity_returns_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.digest import activity_db
    emb = MagicMock()
    emb.name = "ollama"
    emb.dim = 4
    emb.distance = "l2"
    emb.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    db = Path(tmp_path) / "activity.db"
    activity_db.init_db(db, embedder=emb, model="bge-m3")
    rec = activity_db.CommitRecord(
        repo="r", sha="abc123", author="t", subject="feat: x",
        body="", stat_files=1, stat_insertions=1, stat_deletions=0,
        diff_snippet="", committed_at="2026-04-19T00:00:00Z",
    )
    activity_db.insert_commit(db, rec, embedder=emb, model="bge-m3")
    monkeypatch.setattr(
        "claude_almanac.digest.qa.tools.search_activity.make_embedder",
        lambda *a, **kw: emb,
    )
    out = search_activity.search_activity(query="x", top_k=3)
    assert len(out) == 1
    assert out[0]["repo"] == "r"
    assert out[0]["sha"] == "abc123"


def test_git_show_rejects_invalid_sha(monkeypatch):
    out = git_show.git_show(repo="r", sha="NOTASHA")
    assert "error" in out


def test_git_show_resolves_from_config(monkeypatch, tmp_path):
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "a").write_text("hi\n")
    subprocess.run(["git", "add", "a"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add a"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    from claude_almanac.core import config as core_config
    fake_cfg = core_config.default_config()
    fake_cfg.digest.repos = [core_config.RepoCfg(path=str(repo), alias="r")]
    monkeypatch.setattr(
        "claude_almanac.digest.qa.tools.git_show.core_config.load",
        lambda: fake_cfg,
    )
    out = git_show.git_show(repo="r", sha=sha[:10])
    assert "error" not in out
    assert "feat: add a" in out["subject"]


def test_tools_register_on_import():
    r = registry.Registry()
    registry.auto_discover("claude_almanac.digest.qa.tools", registry=r)
    names = {e.name for e in r.all()}
    assert names == {"search_activity", "git_show"}
