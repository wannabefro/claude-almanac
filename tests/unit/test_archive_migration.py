"""Schema migration tests: adding last_used_at/use_count and entries_history
to a v0.3.0-shaped archive DB."""
import sqlite3

import sqlite_vec  # type: ignore[import-untyped]

from claude_almanac.core import archive


def _v030_init(db):
    """Recreate the v0.3.0 schema (pre-decay/versioning)."""
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany(
        "INSERT INTO meta(key, value) VALUES (?, ?)",
        [("embedder", "ollama"), ("model", "bge-m3"),
         ("dim", "2"), ("distance", "l2")],
    )
    conn.execute(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "text TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, "
        "pinned INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE entries_vec USING vec0("
        "id INTEGER PRIMARY KEY, embedding FLOAT[2])"
    )
    conn.commit()
    conn.close()


def test_migration_adds_columns_and_history(tmp_path):
    db = tmp_path / "a.db"
    _v030_init(db)
    # Insert a row under the old schema
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    import struct
    conn.execute(
        "INSERT INTO entries(text, kind, source, pinned, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("existing", "note", "md:foo.md", 0, 1000),
    )
    conn.execute(
        "INSERT INTO entries_vec(id, embedding) VALUES (?, ?)",
        (1, struct.pack("2f", 1.0, 0.0)),
    )
    conn.commit()
    conn.close()

    # Re-init with v0.3.1 code: should add columns + entries_history idempotently
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")

    # Verify columns
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    assert "last_used_at" in cols
    assert "use_count" in cols
    # Existing data preserved
    row = conn.execute(
        "SELECT text, use_count, last_used_at FROM entries WHERE id=1"
    ).fetchone()
    assert row == ("existing", 0, None)
    # entries_history exists
    hist_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(entries_history)").fetchall()
    }
    expected_cols = {
        "slug",
        "text",
        "kind",
        "version",
        "original_created_at",
        "superseded_at",
        "provenance",
    }
    assert expected_cols <= hist_cols
    conn.close()


def test_init_is_idempotent_on_fresh_db(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    # Second init should not raise
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")


def test_migration_is_idempotent_on_v030_db(tmp_path):
    db = tmp_path / "a.db"
    _v030_init(db)
    # First migration
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    # Second migration must be a no-op (no exception, no duplicate-column error)
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    # Schema still correct
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
    assert "last_used_at" in cols
    assert "use_count" in cols
    # entries_history still present and has index
    idxs = {r[1] for r in conn.execute("PRAGMA index_list(entries_history)").fetchall()}
    assert "idx_entries_history_slug" in idxs
    conn.close()
