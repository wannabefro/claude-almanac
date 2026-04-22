"""Incremental doc refresh by file mtime (v0.4).

On each run:

- Compare current on-disk mtimes with the per-file latest ``created_at``
  in the DB (approximation: if any row for the file has ``created_at``
  older than the file mtime, re-ingest the file).
- Re-ingest changed files (full delete + re-insert so stale chunks
  don't linger when a section is removed).
- Delete rows for files no longer on disk.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_almanac.contentindex import db as _db
from claude_almanac.documents.ingest import _discover, index_repo

__all__ = ["refresh_repo"]


def _indexed_files(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            r[0] for r in conn.execute(
                "SELECT DISTINCT file_path FROM entries WHERE kind='doc'"
            ).fetchall() if r[0]
        }
    finally:
        conn.close()


def _file_latest_created_at(db_path: str, file_path: str) -> float | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT created_at FROM entries "
            "WHERE kind='doc' AND file_path=? "
            "ORDER BY created_at DESC LIMIT 1",
            (file_path,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    # created_at is ISO8601 UTC; parse for comparison.
    return datetime.fromisoformat(row[0]).timestamp()


def refresh_repo(
    *,
    repo_root: str,
    db_path: str,
    embedder: Any,
    patterns: list[str],
    excludes: list[str],
    chunk_max_chars: int,
    chunk_overlap_chars: int,
    commit_sha: str,
) -> int:
    """Incremental refresh. Returns the number of chunks re-ingested."""
    current = set(_discover(repo_root, patterns, excludes))
    indexed = _indexed_files(db_path)

    # Delete rows for files no longer on disk.
    gone = indexed - current
    if gone:
        _db.delete_by_file_kind(db_path, kind="doc", file_paths=gone)

    # Identify changed files.
    to_reingest: list[str] = []
    for rel in current:
        abs_path = Path(repo_root) / rel
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            continue
        latest = _file_latest_created_at(db_path, rel)
        if latest is None or mtime > latest:
            to_reingest.append(rel)

    if not to_reingest:
        return 0

    # Delete existing rows for to_reingest files (so chunk removal works
    # cleanly when a doc section was removed).
    _db.delete_by_file_kind(db_path, kind="doc", file_paths=to_reingest)

    # Re-ingest only the changed files.
    return index_repo(
        repo_root=repo_root,
        db_path=db_path,
        embedder=embedder,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        commit_sha=commit_sha,
        only_files=to_reingest,
    )
