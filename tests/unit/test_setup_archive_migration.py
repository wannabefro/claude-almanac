"""Regression test for setup's archive-migration sweep.

v0.3.5 added _migrate_all_archives to catch stale project DBs that
predate v0.3.1's last_used_at column or v0.3.2's edges/rollups tables.
Without this sweep, `recall search-all` crashed the first time it hit
a stale DB.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from claude_almanac.cli import setup as setup_mod


def _seed_pre_v031_archive(db: Path) -> None:
    """Create a minimal v0.3.0-shape archive (no last_used_at, no edges)."""
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        conn.executescript("""
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES
                ('embedder_name', 'ollama'),
                ('model', 'bge-m3'),
                ('dim', '1024'),
                ('distance', 'cosine');
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def test_migrate_all_archives_upgrades_stale_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths as paths_mod
    stale = paths_mod.projects_memory_dir() / "stale-proj" / "archive.db"
    _seed_pre_v031_archive(stale)

    # Pre-state: last_used_at missing
    conn = sqlite3.connect(stale)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    conn.close()
    assert "last_used_at" not in cols

    setup_mod._migrate_all_archives()

    # Post-state: last_used_at + edges table present
    conn = sqlite3.connect(stale)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    edges_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='edges'"
    ).fetchone() is not None
    conn.close()
    assert "last_used_at" in cols
    assert edges_exists


def test_migrate_all_archives_skips_current_schema_db(tmp_path, monkeypatch, capsys):
    """No-op fast-path: current-schema DBs aren't re-migrated + don't print."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import archive
    from claude_almanac.core import paths as paths_mod
    from claude_almanac.embedders.profiles import get
    good = paths_mod.projects_memory_dir() / "fresh-proj" / "archive.db"
    good.parent.mkdir(parents=True, exist_ok=True)
    profile = get("ollama", "bge-m3")
    archive.init(good, embedder_name=profile.provider, model=profile.model,
                 dim=profile.dim, distance=profile.distance)

    setup_mod._migrate_all_archives()
    captured = capsys.readouterr()
    assert "migrated" not in captured.out


def test_migrate_all_archives_handles_empty_projects_dir(tmp_path, monkeypatch):
    """No crash when projects dir is empty or missing."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    # Don't create any project subdirs
    setup_mod._migrate_all_archives()  # must not raise
