import sqlite3

import pytest

from claude_almanac.core.archive import init, insert_rollup, search_rollups

_DIM = 1024


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "a.db"
    init(path, embedder_name="ollama", model="bge-m3", dim=_DIM, distance="l2")
    return path


def test_insert_rollup_roundtrip(db):
    emb = [0.1] * _DIM
    rid = insert_rollup(
        db, session_id="s1", repo_key="r", branch="main",
        started_at=1, ended_at=2, turn_count=5, trigger="session_end",
        narrative="We debugged X.", decisions="[]", artifacts="{}",
        embedding=emb,
    )
    assert rid is not None
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT narrative FROM rollups WHERE id=?", (rid,)).fetchone()
        assert row[0] == "We debugged X."
    finally:
        conn.close()


def test_insert_rollup_duplicate_returns_none(db):
    emb = [0.1] * _DIM
    a = insert_rollup(db, session_id="s1", repo_key="r", branch=None,
                      started_at=1, ended_at=2, turn_count=5, trigger="idle",
                      narrative="n", decisions="[]", artifacts="{}", embedding=emb)
    b = insert_rollup(db, session_id="s1", repo_key="r", branch=None,
                      started_at=1, ended_at=2, turn_count=5, trigger="idle",
                      narrative="n2", decisions="[]", artifacts="{}", embedding=emb)
    assert a is not None
    assert b is None


def test_search_rollups_returns_rows(db):
    emb_a = [1.0] + [0.0] * (_DIM - 1)
    emb_b = [0.0, 1.0] + [0.0] * (_DIM - 2)
    insert_rollup(db, session_id="s1", repo_key="r", branch=None,
                  started_at=1, ended_at=2, turn_count=3, trigger="session_end",
                  narrative="alpha", decisions="[]", artifacts="{}", embedding=emb_a)
    insert_rollup(db, session_id="s2", repo_key="r", branch=None,
                  started_at=1, ended_at=2, turn_count=3, trigger="session_end",
                  narrative="beta", decisions="[]", artifacts="{}", embedding=emb_b)
    results = search_rollups(db, query_embedding=emb_a, topk=2)
    assert len(results) == 2
    # First result should be "alpha" (closer to emb_a).
    assert results[0][2] == "alpha"
