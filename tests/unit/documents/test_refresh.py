"""Incremental refresh: re-ingest changed files, delete rows for gone files."""
from __future__ import annotations

import sqlite3
import time

import pytest

from claude_almanac.contentindex import db as cdb
from claude_almanac.documents import ingest, refresh
from tests.unit.documents.test_ingest import _FakeEmbedder


@pytest.fixture
def base_indexed(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("# A\n\nbody-a.\n")
    (tmp_path / "docs/b.md").write_text("# B\n\nbody-b.\n")
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    ingest.index_repo(
        repo_root=str(tmp_path), db_path=dbp, embedder=_FakeEmbedder(),
        patterns=["docs/**"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200, commit_sha="sha1",
    )
    return tmp_path, dbp


def test_refresh_reindexes_changed_file(base_indexed):
    tmp, dbp = base_indexed
    # Change content of a.md
    time.sleep(0.05)
    (tmp / "docs/a.md").write_text("# A\n\nbody-a-v2.\n")
    n = refresh.refresh_repo(
        repo_root=str(tmp), db_path=dbp, embedder=_FakeEmbedder(),
        patterns=["docs/**"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200, commit_sha="sha2",
    )
    assert n >= 1
    conn = sqlite3.connect(dbp)
    row = conn.execute(
        "SELECT text FROM entries WHERE kind='doc' AND file_path='docs/a.md'"
    ).fetchone()
    assert "body-a-v2" in row[0]


def test_refresh_skips_unchanged_files(base_indexed):
    tmp, dbp = base_indexed
    n = refresh.refresh_repo(
        repo_root=str(tmp), db_path=dbp, embedder=_FakeEmbedder(),
        patterns=["docs/**"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200, commit_sha="sha3",
    )
    assert n == 0  # nothing changed


def test_refresh_deletes_rows_for_removed_file(base_indexed):
    tmp, dbp = base_indexed
    (tmp / "docs/b.md").unlink()
    refresh.refresh_repo(
        repo_root=str(tmp), db_path=dbp, embedder=_FakeEmbedder(),
        patterns=["docs/**"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200, commit_sha="sha4",
    )
    conn = sqlite3.connect(dbp)
    paths = {r[0] for r in conn.execute(
        "SELECT file_path FROM entries WHERE kind='doc'"
    ).fetchall()}
    assert "docs/a.md" in paths
    assert "docs/b.md" not in paths
