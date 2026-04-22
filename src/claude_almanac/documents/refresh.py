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


def _indexed_files_with_mtime(db_path: str) -> dict[str, float]:
    """Single-query fetch of per-file latest ``created_at`` as epoch
    seconds. Replaces the previous N+1 pattern that ran one ``ORDER BY
    created_at`` query per file (`_file_latest_created_at`). For a
    200-file docs tree that's 200 single-row queries per refresh."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT file_path, MAX(created_at) FROM entries "
            "WHERE kind='doc' AND file_path IS NOT NULL "
            "GROUP BY file_path"
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, float] = {}
    for fp, ts in rows:
        if fp and ts:
            # created_at is ISO8601 UTC.
            out[fp] = datetime.fromisoformat(ts).timestamp()
    return out


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
    indexed_mtime = _indexed_files_with_mtime(db_path)

    # Delete rows for files no longer on disk.
    gone = set(indexed_mtime.keys()) - current
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
        db_mtime = indexed_mtime.get(rel)
        if db_mtime is None or mtime > db_mtime:
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
