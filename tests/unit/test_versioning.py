"""Append-only versioning: snapshot prior body to entries_history, UPDATE live row."""
import sqlite3

import pytest
import sqlite_vec  # type: ignore[import-untyped]

from claude_almanac.core import archive, versioning


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "a.db"
    archive.init(path, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    return path


def _scope(tmp_path):
    d = tmp_path / "scope"
    d.mkdir()
    return d


def test_first_write_inserts_no_history(db, tmp_path):
    scope = _scope(tmp_path)
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body-1", new_kind="reference",
        new_embedding=[1.0, 0.0], provenance="write_md",
    )
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    hist = conn.execute("SELECT COUNT(*) FROM entries_history").fetchone()[0]
    live = conn.execute("SELECT COUNT(*) FROM entries WHERE source='md:a.md'").fetchone()[0]
    assert hist == 0
    assert live == 1
    assert (scope / "a.md").read_text() == "body-1"


def test_second_write_snapshots_prior(db, tmp_path):
    scope = _scope(tmp_path)
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body-1", new_kind="reference",
        new_embedding=[1.0, 0.0], provenance="write_md",
    )
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body-2", new_kind="reference",
        new_embedding=[0.9, 0.1], provenance="dedup",
    )
    conn = sqlite3.connect(str(db))
    hist_rows = conn.execute(
        "SELECT text, version, provenance FROM entries_history WHERE slug='a.md' "
        "ORDER BY version"
    ).fetchall()
    assert hist_rows == [("body-1", 1, "dedup")]
    # Still exactly one live row
    live_count = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE source='md:a.md'"
    ).fetchone()[0]
    assert live_count == 1
    live_text = conn.execute(
        "SELECT text FROM entries WHERE source='md:a.md'"
    ).fetchone()[0]
    assert live_text == "body-2"
    assert (scope / "a.md").read_text() == "body-2"


def test_identical_rewrite_is_noop(db, tmp_path):
    scope = _scope(tmp_path)
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body", new_kind="reference",
        new_embedding=[1.0, 0.0], provenance="write_md",
    )
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body", new_kind="reference",
        new_embedding=[1.0, 0.0], provenance="update_md",
    )
    conn = sqlite3.connect(str(db))
    hist = conn.execute("SELECT COUNT(*) FROM entries_history").fetchone()[0]
    live = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert hist == 0
    assert live == 1


def test_version_counter_monotonic(db, tmp_path):
    scope = _scope(tmp_path)
    for i in range(1, 4):
        versioning.snapshot_then_replace(
            db, scope_dir=scope, slug="a.md",
            new_text=f"body-{i}", new_kind="reference",
            new_embedding=[1.0, 0.0], provenance="correct",
        )
    conn = sqlite3.connect(str(db))
    versions = [r[0] for r in conn.execute(
        "SELECT version FROM entries_history WHERE slug='a.md' ORDER BY version"
    ).fetchall()]
    assert versions == [1, 2]  # two history rows (v1, v2); v3 is live


def test_list_versions_returns_history_plus_live(db, tmp_path):
    scope = _scope(tmp_path)
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body-1", new_kind="reference",
        new_embedding=[1.0, 0.0], provenance="write_md",
    )
    versioning.snapshot_then_replace(
        db, scope_dir=scope, slug="a.md",
        new_text="body-2", new_kind="reference",
        new_embedding=[0.9, 0.1], provenance="update_md",
    )
    chain = versioning.list_versions(db, slug="a.md")
    # Newest-first: v2 (live, no superseded_at) then v1 (historical)
    assert [v.text for v in chain] == ["body-2", "body-1"]
    assert chain[0].provenance == "update_md"  # the action that produced body-2
    assert chain[1].provenance == "update_md"  # the action that superseded body-1
