import sqlite3

import pytest

from claude_almanac.core.archive import ensure_schema
from claude_almanac.embedders.profiles import get


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "archive.db"
    c = sqlite3.connect(str(db))
    c.enable_load_extension(True)
    import sqlite_vec
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    yield c
    c.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    sql = "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')"
    rows = conn.execute(sql).fetchall()
    return {r[0] for r in rows}


def test_rollups_table_created(conn):
    ensure_schema(conn, profile=get("ollama", "bge-m3"))
    assert "rollups" in _tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(rollups)").fetchall()}
    expected = {"id", "session_id", "repo_key", "branch", "started_at", "ended_at",
                "turn_count", "trigger", "narrative", "decisions", "artifacts", "created_at"}
    assert expected <= cols


def test_rollups_vec_created_with_embedder_dim(conn):
    profile = get("ollama", "bge-m3")
    ensure_schema(conn, profile=profile)
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='rollups_vec'"
    ).fetchone()
    assert sql is not None
    assert f"FLOAT[{profile.dim}]" in sql[0]


def test_edges_table_created(conn):
    ensure_schema(conn, profile=get("ollama", "bge-m3"))
    assert "edges" in _tables(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(edges)").fetchall()}
    expected = {"id", "src_id", "src_scope", "dst_id", "dst_scope",
                "type", "created_at", "created_by"}
    assert expected <= cols


def test_edges_unique_constraint(conn):
    ensure_schema(conn, profile=get("ollama", "bge-m3"))
    conn.execute(
        "INSERT INTO edges (src_id, src_scope, dst_id, dst_scope, type, created_at, created_by)"
        " VALUES (1, 'entry@project', 2, 'entry@project', 'related', 1, 'curator')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO edges (src_id, src_scope, dst_id, dst_scope, type, created_at, created_by)"
            " VALUES (1, 'entry@project', 2, 'entry@project', 'related', 2, 'user')"
        )


def test_rollups_unique_session_trigger(conn):
    ensure_schema(conn, profile=get("ollama", "bge-m3"))
    conn.execute(
        "INSERT INTO rollups (session_id, repo_key, started_at, ended_at, turn_count,"
        " trigger, narrative, decisions, artifacts, created_at)"
        " VALUES ('s1', 'r', 1, 2, 3, 'session_end', 'n', '[]', '{}', 10)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO rollups (session_id, repo_key, started_at, ended_at, turn_count,"
            " trigger, narrative, decisions, artifacts, created_at)"
            " VALUES ('s1', 'r', 1, 2, 3, 'session_end', 'n2', '[]', '{}', 11)"
        )


def test_ensure_schema_is_idempotent(conn):
    profile = get("ollama", "bge-m3")
    ensure_schema(conn, profile=profile)
    ensure_schema(conn, profile=profile)  # must not raise
    assert "rollups" in _tables(conn)
