"""Requires: Ollama running locally with bge-m3 pulled. Marked as `integration`."""
import os
import pytest
from pathlib import Path


pytestmark = pytest.mark.integration


@pytest.fixture
def tmp_install(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import paths
    paths.ensure_dirs()
    return tmp_path


def test_retrieve_end_to_end_empty_returns_no_block(tmp_install):
    from claude_almanac.core import retrieve
    out = retrieve.run("anything")
    assert out == ""  # no memories yet, no injection


def test_curator_round_trip(tmp_install):
    from claude_almanac.core import curator, paths
    decisions = [{
        "action": "write_md", "scope": "global", "slug": "project_test.md",
        "kind": "project", "text": "project_test: just a test memory body",
    }]
    curator._apply_decisions(decisions)
    assert (paths.global_memory_dir() / "project_test.md").exists()


def test_recall_search_returns_hit_after_write(tmp_install, capsys):
    from claude_almanac.core import curator
    from claude_almanac.cli import recall
    decisions = [{
        "action": "write_md", "scope": "global", "slug": "project_auth.md",
        "kind": "project", "text": "auth middleware lives in api/auth.py",
    }]
    curator._apply_decisions(decisions)
    recall.run(["search", "authentication"])
    assert "auth" in capsys.readouterr().out.lower()
