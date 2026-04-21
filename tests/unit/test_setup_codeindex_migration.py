"""Regression tests for setup's code-index dim-mismatch sweep.

A content-index.db created with a wrong embedding dim (old installs had
a default-2 placeholder) is unusable — every query raises
`sqlite3.OperationalError: Dimension mismatch`. Setup now renames these
aside so users can re-init cleanly.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from claude_almanac.cli import setup as setup_mod


def _seed_codeindex_db(db: Path, dim: int) -> None:
    """Create a minimal content-index.db with the given vec dim."""
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.executescript(f"""
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                file_path TEXT,
                symbol_name TEXT,
                module TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                commit_sha TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE entries_vec USING vec0(embedding FLOAT[{dim}]);
        """)
        conn.commit()
    finally:
        conn.close()


def test_detect_code_index_dim_returns_dim(tmp_path):
    db = tmp_path / "content-index.db"
    _seed_codeindex_db(db, dim=1024)
    assert setup_mod._detect_code_index_dim(db) == 1024


def test_detect_code_index_dim_handles_nonexistent():
    assert setup_mod._detect_code_index_dim(Path("/nope/content-index.db")) is None


def test_migrate_renames_stale_dim_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import paths as paths_mod
    # Seed a stale DB with wrong dim (2 — the old bug).
    stale_root = paths_mod.projects_memory_dir() / "stale-proj"
    stale_db = stale_root / "content-index.db"
    _seed_codeindex_db(stale_db, dim=2)
    assert stale_db.exists()

    setup_mod._migrate_all_code_indexes()

    # Original file gone; sibling `.stale-2` present.
    assert not stale_db.exists()
    assert (stale_root / "content-index.db.stale-2").exists()
    out = capsys.readouterr().out
    assert "content-index.db.stale-2" in out


def test_migrate_leaves_matching_dim_db_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import paths as paths_mod
    from claude_almanac.embedders.profiles import get
    good_root = paths_mod.projects_memory_dir() / "good-proj"
    good_db = good_root / "content-index.db"
    # Seed at the DEFAULT embedder's dim so the DB is considered "matching"
    # by _migrate_all_code_indexes under test isolation.
    from claude_almanac.core.config import default_config
    default_model = default_config().embedder.model
    profile = get("ollama", default_model)
    _seed_codeindex_db(good_db, dim=profile.dim)

    setup_mod._migrate_all_code_indexes()

    # Unchanged.
    assert good_db.exists()
    assert not (good_root / "content-index.db.stale-1024").exists()
    assert "renamed" not in capsys.readouterr().out


def test_migrate_handles_empty_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    setup_mod._migrate_all_code_indexes()  # must not raise
