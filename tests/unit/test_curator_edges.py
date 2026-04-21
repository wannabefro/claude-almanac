"""Tests for curator edge emission: related edges from JSON + supersedes on body change."""
from __future__ import annotations

import sqlite3

from claude_almanac.core import archive, config, curator, paths
from claude_almanac.core.archive import lookup_entry_id_by_slug

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

class _FakeEmbedder:
    name, model, dim, distance = "ollama", "bge-m3", 2, "l2"

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _open_conn(db_path) -> sqlite3.Connection:
    import sqlite_vec  # type: ignore[import-untyped]

    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _setup(monkeypatch, tmp_path, *, dedup_return=(None, 99.0)):
    """Common monkeypatching for _apply_decisions tests.

    Returns (db_path, scope_dir).
    """
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    cfg = config.default_config()
    config.save(cfg)

    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder",
        lambda *a, **k: _FakeEmbedder(),
    )

    dedup_val = dedup_return

    monkeypatch.setattr(
        "claude_almanac.core.dedup.find_dup_slug",
        lambda *, db, embedding, threshold: dedup_val,
    )

    scope_dir = paths.project_memory_dir()
    scope_dir.mkdir(parents=True, exist_ok=True)
    db = scope_dir / "archive.db"
    return db, scope_dir


# ---------------------------------------------------------------------------
# lookup_entry_id_by_slug
# ---------------------------------------------------------------------------


def test_lookup_entry_id_by_slug_returns_id(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    row_id = archive.insert_entry(
        db, text="hello", kind="project", source="md:some_slug.md",
        pinned=True, embedding=[1.0, 0.0],
    )
    conn = _open_conn(db)
    try:
        result = lookup_entry_id_by_slug(conn, "some_slug.md")
    finally:
        conn.close()
    assert result == row_id


def test_lookup_entry_id_by_slug_returns_none_for_missing(tmp_path):
    db = tmp_path / "a.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    conn = _open_conn(db)
    try:
        result = lookup_entry_id_by_slug(conn, "nonexistent.md")
    finally:
        conn.close()
    assert result is None


# ---------------------------------------------------------------------------
# related edges from write_md / update_md JSON `edges` field
# ---------------------------------------------------------------------------


def test_write_md_with_edges_inserts_related_edge(monkeypatch, tmp_path):
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    # First write seeds a sibling entry so it has a real ID.
    curator._apply_decisions([
        {
            "action": "write_md", "slug": "sibling.md",
            "text": "sibling content", "kind": "reference",
        },
    ])

    # Second write references the sibling via edges.
    curator._apply_decisions([
        {
            "action": "write_md",
            "slug": "new_slug.md",
            "text": "references sibling",
            "kind": "project",
            "edges": [{"type": "related", "to": "sibling.md"}],
        }
    ])

    conn = _open_conn(db)
    try:
        rows = conn.execute(
            "SELECT src_id, dst_id, type, created_by FROM edges"
        ).fetchall()
    finally:
        conn.close()

    related = [r for r in rows if r[2] == "related"]
    assert len(related) == 1
    assert related[0][2] == "related"
    assert related[0][3] == "curator"


def test_write_md_edges_to_unknown_slug_silently_dropped(monkeypatch, tmp_path):
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    curator._apply_decisions([
        {
            "action": "write_md",
            "slug": "new_slug.md",
            "text": "content",
            "kind": "project",
            "edges": [{"type": "related", "to": "does_not_exist.md"}],
        }
    ])

    conn = _open_conn(db)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    finally:
        conn.close()

    assert rows == 0


def test_write_md_non_related_edge_type_silently_dropped(monkeypatch, tmp_path):
    """Curator JSON may only emit 'related' edges; other types must be ignored."""
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    # Seed a target entry first.
    curator._apply_decisions([
        {"action": "write_md", "slug": "target.md", "text": "target body", "kind": "reference"},
    ])

    curator._apply_decisions([
        {
            "action": "write_md",
            "slug": "new_slug.md",
            "text": "content",
            "kind": "project",
            "edges": [{"type": "supersedes", "to": "target.md"}],  # not allowed
        }
    ])

    conn = _open_conn(db)
    try:
        rows = conn.execute(
            "SELECT type FROM edges"
        ).fetchall()
    finally:
        conn.close()

    # No supersedes edge should have been created via the curator JSON path.
    assert not any(r[0] == "supersedes" for r in rows)


def test_update_md_with_edges_inserts_related_edge(monkeypatch, tmp_path):
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    # Seed both the target entry and the one being updated.
    curator._apply_decisions([
        {"action": "write_md", "slug": "sibling.md", "text": "sibling body", "kind": "reference"},
        {"action": "write_md", "slug": "updatable.md", "text": "original body", "kind": "project"},
    ])

    curator._apply_decisions([
        {
            "action": "update_md",
            "slug": "updatable.md",
            "text": "updated body",
            "kind": "project",
            "edges": [{"type": "related", "to": "sibling.md"}],
        }
    ])

    conn = _open_conn(db)
    try:
        related_rows = conn.execute(
            "SELECT type, created_by FROM edges WHERE type='related'"
        ).fetchall()
    finally:
        conn.close()

    assert len(related_rows) >= 1
    assert all(r[1] == "curator" for r in related_rows)


# ---------------------------------------------------------------------------
# supersedes edges emitted automatically on body change
# ---------------------------------------------------------------------------


def test_update_md_emits_supersedes_edge_when_body_changes(monkeypatch, tmp_path):
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    # First write — no supersedes edge (no prior body).
    curator._apply_decisions([
        {"action": "write_md", "slug": "old.md", "text": "original body", "kind": "project"},
    ])

    # Second write with a different body — should emit supersedes.
    curator._apply_decisions([
        {"action": "update_md", "slug": "old.md", "text": "new body", "kind": "project"},
    ])

    conn = _open_conn(db)
    try:
        edges = conn.execute(
            "SELECT type, created_by FROM edges"
        ).fetchall()
        hist_rows = conn.execute(
            "SELECT id FROM entries_history WHERE slug='old.md'"
        ).fetchall()
    finally:
        conn.close()

    supersedes = [r for r in edges if r[0] == "supersedes"]
    assert len(supersedes) == 1
    assert supersedes[0][1] == "curator"
    # There should be exactly one history row for this slug.
    assert len(hist_rows) == 1


def test_update_md_does_not_emit_supersedes_when_body_unchanged(monkeypatch, tmp_path):
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    curator._apply_decisions([
        {"action": "write_md", "slug": "same.md", "text": "body B", "kind": "project"},
    ])

    # Re-write with identical body — snapshot_then_replace is a no-op,
    # and no supersedes edge should be emitted.
    curator._apply_decisions([
        {"action": "update_md", "slug": "same.md", "text": "body B", "kind": "project"},
    ])

    conn = _open_conn(db)
    try:
        edges = conn.execute(
            "SELECT type FROM edges WHERE type='supersedes'"
        ).fetchall()
    finally:
        conn.close()

    assert len(edges) == 0


def test_first_write_does_not_emit_supersedes(monkeypatch, tmp_path):
    """First write has no prior body, so no supersedes edge."""
    db, scope_dir = _setup(monkeypatch, tmp_path, dedup_return=(None, 99.0))

    curator._apply_decisions([
        {"action": "write_md", "slug": "brand_new.md", "text": "first body", "kind": "project"},
    ])

    conn = _open_conn(db)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE type='supersedes'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert rows == 0
