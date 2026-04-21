"""Tests for recall edge management subcommands: link, supersede, unlink, links."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_almanac.cli import recall as cli_recall
from claude_almanac.core.archive import init, insert_entry
from claude_almanac.embedders.profiles import get


@pytest.fixture
def project_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    # Initialize the archive in the XDG project memory dir.
    from claude_almanac.core.paths import project_memory_dir
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
    # Seed two entries that the edge tests can connect.
    emb = [0.1] * profile.dim
    insert_entry(
        db,
        text="foo body",
        kind="project",
        source="md:foo",
        pinned=False,
        embedding=emb,
    )
    insert_entry(
        db,
        text="bar body",
        kind="project",
        source="md:bar",
        pinned=False,
        embedding=emb,
    )
    return db


def _count_edges(db: Path) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT count(*) FROM edges").fetchone()[0]
    finally:
        conn.close()


def test_link_inserts_related_edges_symmetric(project_db, capsys):
    cli_recall.run(["link", "foo", "bar"])
    out = capsys.readouterr().out
    assert out  # some confirmation echoed
    # Symmetric: both directions inserted.
    assert _count_edges(project_db) == 2


def test_link_errors_on_unknown_slug(project_db, capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli_recall.run(["link", "foo", "nope"])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "unknown" in err.lower() or "error" in err.lower()


def test_supersede_inserts_one_directional_edge(project_db, capsys):
    cli_recall.run(["supersede", "bar", "foo"])
    capsys.readouterr()
    assert _count_edges(project_db) == 1
    conn = sqlite3.connect(project_db)
    try:
        row = conn.execute(
            "SELECT type, created_by FROM edges LIMIT 1"
        ).fetchone()
        assert row[0] == "supersedes"
        assert row[1] == "user"
    finally:
        conn.close()


def test_unlink_removes_both_directions_for_related(project_db, capsys):
    cli_recall.run(["link", "foo", "bar"])
    capsys.readouterr()
    assert _count_edges(project_db) == 2
    cli_recall.run(["unlink", "foo", "bar"])
    capsys.readouterr()
    assert _count_edges(project_db) == 0


def test_links_shows_outgoing_and_incoming(project_db, capsys):
    cli_recall.run(["link", "foo", "bar"])
    capsys.readouterr()
    cli_recall.run(["links", "foo"])
    out = capsys.readouterr().out
    # Some form of heading / arrow should appear
    assert "Outgoing" in out or "outgoing" in out.lower()
    assert "Incoming" in out or "incoming" in out.lower()
