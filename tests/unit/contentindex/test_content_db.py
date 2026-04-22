"""Locks the v0.4 schema additions: kind='doc' rows + their unique index."""
from __future__ import annotations

import pytest

from claude_almanac.contentindex import db as cdb


def test_doc_rows_upsert_and_roundtrip(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    rid = cdb.upsert(
        dbp, kind="doc",
        text="// docs/foo.md [doc] Intro\n# Intro\n\nBody.",
        file_path="docs/foo.md",
        symbol_name="Intro",
        module="docs",
        line_start=1, line_end=3,
        commit_sha="sha1",
        embedding=[0.1, 0.2, 0.3, 0.4],
    )
    assert rid >= 1
    rows = cdb.search(dbp, embedding=[0.1, 0.2, 0.3, 0.4], k=5, kind="doc")
    assert len(rows) == 1
    assert rows[0]["symbol_name"] == "Intro"
    assert rows[0]["kind"] == "doc"


def test_doc_unique_index_dedup_on_file_and_line_start(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    cdb.upsert(
        dbp, kind="doc",
        text="v1", file_path="docs/foo.md", symbol_name="Intro",
        module="docs", line_start=1, line_end=3, commit_sha="sha1",
        embedding=[0.1, 0.1, 0.1, 0.1],
    )
    # Second upsert with same (file_path, line_start) replaces the first.
    cdb.upsert(
        dbp, kind="doc",
        text="v2", file_path="docs/foo.md", symbol_name="Intro (revised)",
        module="docs", line_start=1, line_end=5, commit_sha="sha2",
        embedding=[0.2, 0.2, 0.2, 0.2],
    )
    rows = cdb.search(dbp, embedding=[0.2, 0.2, 0.2, 0.2], k=5, kind="doc")
    assert len(rows) == 1
    assert rows[0]["text"] == "v2"
    assert rows[0]["symbol_name"] == "Intro (revised)"
    assert rows[0]["line_end"] == 5


def test_sym_doc_arch_kinds_coexist(tmp_path):
    """All three kinds live in one entries table; kind filter in search works."""
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    cdb.upsert(dbp, kind="sym", text="def f(): ...",
               file_path="a.py", symbol_name="f", module="a",
               line_start=1, line_end=1, commit_sha="s",
               embedding=[0.5, 0, 0, 0])
    cdb.upsert(dbp, kind="doc", text="doc body",
               file_path="docs/a.md", symbol_name="Intro", module="docs",
               line_start=1, line_end=1, commit_sha="s",
               embedding=[0, 0.5, 0, 0])
    cdb.upsert(dbp, kind="arch", text="summary",
               file_path=None, symbol_name=None, module="a",
               line_start=None, line_end=None, commit_sha="s",
               embedding=[0, 0, 0.5, 0])
    assert len(cdb.search(dbp, embedding=[0.5, 0, 0, 0], k=5, kind="sym")) == 1
    assert len(cdb.search(dbp, embedding=[0, 0.5, 0, 0], k=5, kind="doc")) == 1
    assert len(cdb.search(dbp, embedding=[0, 0, 0.5, 0], k=5, kind="arch")) == 1


def test_upsert_sym_rejects_null_symbol_name(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    with pytest.raises(ValueError, match="symbol_name"):
        cdb.upsert(
            dbp, kind="sym", text="def f(): ...",
            file_path="a.py", symbol_name=None, module="a",
            line_start=1, line_end=1, commit_sha="s",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )


def test_upsert_sym_rejects_null_file_path(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    with pytest.raises(ValueError, match="file_path"):
        cdb.upsert(
            dbp, kind="sym", text="def f(): ...",
            file_path=None, symbol_name="f", module="a",
            line_start=1, line_end=1, commit_sha="s",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )


def test_upsert_doc_rejects_null_file_path(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    with pytest.raises(ValueError, match="file_path"):
        cdb.upsert(
            dbp, kind="doc", text="doc body",
            file_path=None, symbol_name="Intro", module="docs",
            line_start=1, line_end=3, commit_sha="s",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )


def test_upsert_doc_rejects_null_line_start(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    with pytest.raises(ValueError, match="line_start"):
        cdb.upsert(
            dbp, kind="doc", text="doc body",
            file_path="docs/foo.md", symbol_name="Intro", module="docs",
            line_start=None, line_end=3, commit_sha="s",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )


def test_delete_by_file_kind_purges_entries_and_vec(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    cdb.upsert(dbp, kind="doc", text="a", file_path="docs/a.md",
               symbol_name="A", module="docs",
               line_start=1, line_end=2, commit_sha="s", embedding=[0.1]*4)
    cdb.upsert(dbp, kind="doc", text="b", file_path="docs/b.md",
               symbol_name="B", module="docs",
               line_start=1, line_end=2, commit_sha="s", embedding=[0.2]*4)
    # Sym row with same file_path as a doc — kind filter should spare it.
    cdb.upsert(dbp, kind="sym", text="def a(): ...", file_path="docs/a.md",
               symbol_name="a", module="docs",
               line_start=3, line_end=5, commit_sha="s", embedding=[0.3]*4)
    deleted = cdb.delete_by_file_kind(
        dbp, kind="doc", file_paths=["docs/a.md"]
    )
    assert deleted == 1
    import sqlite3
    conn = sqlite3.connect(dbp)
    # docs/a.md doc row gone
    assert conn.execute(
        "SELECT COUNT(*) FROM entries WHERE kind='doc' AND file_path='docs/a.md'"
    ).fetchone()[0] == 0
    # docs/b.md doc row still there
    assert conn.execute(
        "SELECT COUNT(*) FROM entries WHERE kind='doc' AND file_path='docs/b.md'"
    ).fetchone()[0] == 1
    # sym row on docs/a.md spared (kind filter)
    assert conn.execute(
        "SELECT COUNT(*) FROM entries WHERE kind='sym' AND file_path='docs/a.md'"
    ).fetchone()[0] == 1


def test_upsert_arch_rejects_null_module(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    with pytest.raises(ValueError, match="module"):
        cdb.upsert(
            dbp, kind="arch", text="summary",
            file_path=None, symbol_name=None, module="",
            line_start=None, line_end=None, commit_sha="s",
            embedding=[0.1, 0.2, 0.3, 0.4],
        )
