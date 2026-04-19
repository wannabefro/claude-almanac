"""Integration smoke: real Ollama, real sqlite-vec, real extractor dispatch.

Proves `codeindex init` → autoinject retrieve surfaces the indexed symbol.
Requires Ollama running with `bge-m3` pulled.
"""
from __future__ import annotations

import subprocess

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tmp_install(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    # Chdir into the temp repo so paths.project_key() resolves the test repo
    # consistently for both init (write) and retrieve (read).
    monkeypatch.chdir(tmp_path)
    from claude_almanac.core import paths
    paths.ensure_dirs()
    return tmp_path


def _make_git_repo(root):
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "x"],
        cwd=root, check=True, capture_output=True, env=env,
    )


def test_init_then_autoinject_retrieves_symbol(tmp_install):
    _make_git_repo(tmp_install)
    (tmp_install / ".claude").mkdir()
    (tmp_install / ".claude" / "code-index.yaml").write_text(
        "default_branch: main\nmodules:\n  patterns: ['src']\n"
    )
    (tmp_install / "src").mkdir()
    (tmp_install / "src" / "auth.py").write_text(
        "def verify_token(token):\n"
        "    '''Validate a bearer token.'''\n"
        "    return token == 'ok'\n"
    )

    from claude_almanac.codeindex import init as ci_init
    assert ci_init.main(str(tmp_install)) == 0

    from claude_almanac.core import retrieve
    out = retrieve.run("where is `verify_token` defined in auth.py?")
    assert "Relevant code" in out
    assert "verify_token" in out
