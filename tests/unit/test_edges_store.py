import sqlite3

import pytest

from claude_almanac.core.archive import ensure_schema
from claude_almanac.edges.store import (
    cascade_delete_on_entry,
    delete_edge,
    insert_edge,
    neighbors,
)
from claude_almanac.embedders.profiles import get


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "archive.db"
    c = sqlite3.connect(str(db))
    c.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    ensure_schema(c, profile=get("ollama", "bge-m3"))
    yield c
    c.close()


def test_insert_and_neighbor_roundtrip(conn):
    eid = insert_edge(conn, src_id=1, src_scope="entry@project",
                      dst_id=2, dst_scope="entry@project",
                      type="related", created_by="curator")
    assert eid > 0
    results = neighbors(conn, [(1, "entry@project")], type="related")
    assert len(results) == 1
    assert results[0].dst_id == 2


def test_duplicate_insert_is_idempotent(conn):
    a = insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "curator")
    b = insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "user")
    assert a == b


def test_delete_edge(conn):
    insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "curator")
    delete_edge(conn, 1, "entry@project", 2, "entry@project", "related")
    assert neighbors(conn, [(1, "entry@project")], type="related") == []


def test_neighbors_filters_by_type(conn):
    insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "curator")
    insert_edge(conn, 1, "entry@project", 3, "entry@project", "supersedes", "curator")
    related = neighbors(conn, [(1, "entry@project")], type="related")
    supers = neighbors(conn, [(1, "entry@project")], type="supersedes")
    assert [e.dst_id for e in related] == [2]
    assert [e.dst_id for e in supers] == [3]


def test_neighbors_no_type_filter_returns_all(conn):
    insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "curator")
    insert_edge(conn, 1, "entry@project", 3, "entry@project", "supersedes", "curator")
    all_edges = neighbors(conn, [(1, "entry@project")])
    assert len(all_edges) == 2


def test_cascade_delete_on_entry(conn):
    insert_edge(conn, 1, "entry@project", 2, "entry@project", "related", "curator")
    insert_edge(conn, 3, "entry@project", 1, "entry@project", "supersedes", "user")
    insert_edge(conn, 5, "entry@project", 6, "entry@project", "related", "curator")
    cascade_delete_on_entry(conn, entry_id=1, scope="entry@project")
    assert neighbors(conn, [(1, "entry@project")], type="related") == []
    rows = conn.execute("SELECT count(*) FROM edges").fetchone()
    assert rows[0] == 1  # only (5 → 6) survives
