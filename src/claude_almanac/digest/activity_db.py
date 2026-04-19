"""activity.db schema + ops for daily digest commits.

Shares `core.archive`'s meta-table contract so the embedder cannot silently
drift between archive.db and activity.db. Uses an Embedder instance for the
embed path rather than subprocessing an external script.
"""
from __future__ import annotations

import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path

import sqlite_vec  # type: ignore[import-untyped]

from ..core import archive
from ..embedders.base import Embedder


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=5.0)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db: Path, *, embedder: Embedder, model: str) -> None:
    """Create schema if absent; raise EmbedderMismatch if existing meta disagrees."""
    # Delegate meta handling to core.archive (single source of truth for the
    # embedder contract). archive.init creates `meta`, `entries`, `entries_vec`
    # — we ignore the entries schema and add our own memories + activity_meta
    # tables. Both schemas coexist; queries target only their own table.
    archive.init(
        db, embedder_name=embedder.name, model=model,
        dim=embedder.dim, distance=embedder.distance,
    )
    conn = _connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              kind TEXT NOT NULL,
              source TEXT UNIQUE,
              text TEXT NOT NULL,
              metadata TEXT,
              pinned INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
            CREATE TABLE IF NOT EXISTS activity_meta (
              id              INTEGER PRIMARY KEY REFERENCES memories(id)
                                      ON DELETE CASCADE,
              repo            TEXT NOT NULL,
              sha             TEXT NOT NULL,
              author          TEXT,
              stat_files      INTEGER,
              stat_insertions INTEGER,
              stat_deletions  INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_activity_meta_repo
                ON activity_meta(repo);
            """
        )
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec "
            f"USING vec0(embedding float[{embedder.dim}])"
        )
        conn.commit()
    finally:
        conn.close()


@dataclass
class CommitRecord:
    repo: str
    sha: str
    author: str
    subject: str
    body: str
    stat_files: int
    stat_insertions: int
    stat_deletions: int
    diff_snippet: str
    committed_at: str


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _commit_text(rec: CommitRecord) -> str:
    stat = (
        f"{rec.stat_files} files, "
        f"+{rec.stat_insertions}/-{rec.stat_deletions}"
    )
    parts = [rec.subject]
    if rec.body:
        parts.append(rec.body)
    parts.append(stat)
    if rec.diff_snippet:
        parts.append(rec.diff_snippet[:2048])
    return "\n\n".join(parts)


def insert_commit(
    db: Path, rec: CommitRecord, *, embedder: Embedder, model: str,
) -> bool:
    """Insert one commit; return True if new, False if duplicate source."""
    archive.assert_compatible(
        db, embedder_name=embedder.name, model=model, dim=embedder.dim,
    )
    source = f"git:{rec.repo}:{rec.sha}"
    conn = _connect(db)
    try:
        existing = conn.execute(
            "SELECT id FROM memories WHERE source = ?", (source,),
        ).fetchone()
        if existing:
            return False
        text = _commit_text(rec)
        [vec] = embedder.embed([text])
        if len(vec) != embedder.dim:
            raise RuntimeError(
                f"embedder returned {len(vec)}d, expected {embedder.dim}d"
            )
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cur = conn.execute(
            """INSERT INTO memories(created_at, updated_at, kind, source,
                                    text, metadata, pinned)
               VALUES (?, ?, 'activity', ?, ?, NULL, 0)""",
            (rec.committed_at, now, source, text),
        )
        rowid = cur.lastrowid
        conn.execute(
            "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
            (rowid, _pack(vec)),
        )
        conn.execute(
            """INSERT INTO activity_meta(id, repo, sha, author,
                                         stat_files, stat_insertions,
                                         stat_deletions)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rowid, rec.repo, rec.sha, rec.author,
             rec.stat_files, rec.stat_insertions, rec.stat_deletions),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def prune_activity(db: Path, *, retention_days: int = 30) -> int:
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() - retention_days * 86400),
    )
    conn = _connect(db)
    try:
        ids = [r[0] for r in conn.execute(
            """SELECT id FROM memories
               WHERE kind='activity' AND pinned=0 AND created_at < ?""",
            (cutoff,),
        ).fetchall()]
        for i in ids:
            conn.execute("DELETE FROM memories_vec WHERE rowid=?", (i,))
            conn.execute("DELETE FROM memories WHERE id=?", (i,))
        conn.commit()
        return len(ids)
    finally:
        conn.close()
