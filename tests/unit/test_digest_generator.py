import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_almanac.digest import generator


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(data))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(cfg))
    (data / "global").mkdir(parents=True)
    (data / "projects").mkdir(parents=True)
    (data / "digests").mkdir(parents=True)
    return data, cfg


def _fake_embedder():
    emb = MagicMock()
    emb.name = "ollama"
    emb.dim = 4
    emb.distance = "l2"
    emb.embed.return_value = [[0.1, 0.2, 0.3, 0.4]]
    return emb


def test_generate_writes_markdown_and_inserts_commits(setup_env, tmp_path, monkeypatch):
    data, _cfg = setup_env
    # Set up one repo with one commit.
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add a"], cwd=repo, check=True, capture_output=True)

    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path=str(repo), alias="r")]

    emb = _fake_embedder()
    monkeypatch.setattr(
        "claude_almanac.digest.generator.make_embedder",
        lambda *a, **kw: emb,
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.haiku_narrate",
        lambda **kw: "- did things",
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.digest_notify",
        MagicMock(notify=lambda **kw: True),
    )

    result = generator.generate(cfg=cfg, date="2026-04-19")
    assert Path(result["digest_path"]).exists()
    assert result["commits_inserted"] == 1
    body = Path(result["digest_path"]).read_text()
    assert "feat: add a" in body or "did things" in body


def test_generate_repo_filter_writes_per_repo_file(setup_env, tmp_path, monkeypatch):
    data, _cfg = setup_env
    import subprocess
    repo = tmp_path / "r1"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "a").write_text("x")
    subprocess.run(["git", "add", "a"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "x"], cwd=repo, check=True, capture_output=True)

    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path=str(repo), alias="r1")]

    emb = _fake_embedder()
    monkeypatch.setattr(
        "claude_almanac.digest.generator.make_embedder",
        lambda *a, **kw: emb,
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.haiku_narrate",
        lambda **kw: "- x",
    )
    monkeypatch.setattr(
        "claude_almanac.digest.generator.digest_notify.notify",
        lambda **kw: False,
    )

    result = generator.generate(
        cfg=cfg, date="2026-04-19", repo_filter="r1", notify=False,
    )
    path = Path(result["digest_path"])
    assert path.name == "2026-04-19_r1.md"


def test_generate_raises_on_invalid_repo_filter(setup_env, monkeypatch):
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path="/tmp/x", alias="ok")]
    emb = _fake_embedder()
    monkeypatch.setattr(
        "claude_almanac.digest.generator.make_embedder",
        lambda *a, **kw: emb,
    )
    with pytest.raises(ValueError):
        generator.generate(cfg=cfg, repo_filter="../evil")
