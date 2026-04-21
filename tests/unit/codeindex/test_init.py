import subprocess
from unittest.mock import MagicMock, patch

from claude_almanac.codeindex import init as ci_init


def _init_git_repo(path):
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "x",
                    "--author", "t <t@t>"], cwd=path, check=True,
                   capture_output=True, env={"GIT_AUTHOR_NAME": "t",
                                             "GIT_AUTHOR_EMAIL": "t@t",
                                             "GIT_COMMITTER_NAME": "t",
                                             "GIT_COMMITTER_EMAIL": "t@t",
                                             "PATH": "/usr/bin:/bin"})


def test_init_creates_db_and_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    _init_git_repo(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "code-index.yaml").write_text(
        "default_branch: main\nmodules:\n  patterns: ['src']\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f(): pass\n")

    fake_embedder = MagicMock()
    fake_embedder.dim = 2
    fake_embedder.embed.side_effect = lambda texts: [[1.0, 0.0] for _ in texts]
    with patch("claude_almanac.codeindex.init._make_embedder",
               return_value=fake_embedder):
        rc = ci_init.main(str(tmp_path))
    assert rc == 0

    from claude_almanac.core import paths
    dbp = paths.project_memory_dir() / "content-index.db"
    assert dbp.exists()
    assert (paths.project_memory_dir() / "repo_root").read_text() == str(tmp_path)
