"""Tests for recall rollup subcommands: rollups, rollup-now."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from claude_almanac.cli import recall as cli_recall


@pytest.fixture
def project_db_with_rollup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core.archive import init, insert_rollup
    from claude_almanac.core.paths import project_memory_dir
    from claude_almanac.embedders.profiles import get

    project_memory_dir().mkdir(parents=True, exist_ok=True)
    db = project_memory_dir() / "archive.db"
    profile = get("ollama", "bge-m3")
    init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )
    emb = [1.0] + [0.0] * (profile.dim - 1)
    insert_rollup(
        db,
        session_id="s1",
        repo_key="r",
        branch=None,
        started_at=1,
        ended_at=2,
        turn_count=5,
        trigger="session_end",
        narrative="We debugged auth flow.",
        decisions="[]",
        artifacts="{}",
        embedding=emb,
    )
    return db


def test_rollups_search_returns_matching_narrative(
    project_db_with_rollup, capsys, monkeypatch
):
    from claude_almanac.embedders.profiles import get

    profile = get("ollama", "bge-m3")
    fake_emb = [1.0] + [0.0] * (profile.dim - 1)
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [fake_emb]
    monkeypatch.setattr(
        "claude_almanac.cli.recall.make_embedder", lambda *a, **kw: fake_embedder
    )
    cli_recall.run(["rollups", "auth flow debug"])
    out = capsys.readouterr().out
    assert "debugged" in out


def test_rollup_now_errors_when_no_transcripts_dir(tmp_path, monkeypatch, capsys):
    """With no transcripts dir, rollup-now should exit non-zero with a friendly error."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        cli_recall.run(["rollup-now"])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "transcript" in err.lower()
