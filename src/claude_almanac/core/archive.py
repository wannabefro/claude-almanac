"""sqlite-vec-backed archive: pinned md-sourced + ephemeral turn memories."""
from __future__ import annotations

import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import sqlite_vec  # type: ignore[import-untyped]

Distance = Literal["l2", "cosine"]


class EmbedderMismatch(Exception):
    pass


@dataclass
class Hit:
    id: int
    text: str
    kind: str
    source: str
    pinned: bool
    created_at: int
    distance: float
    last_used_at: int | None = None
    use_count: int = 0


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init(db: Path, *, embedder_name: str, model: str, dim: int, distance: Distance) -> None:
    conn = _connect(db)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        existing = {row[0]: row[1] for row in conn.execute("SELECT key, value FROM meta")}
        if existing:
            if (
                existing.get("embedder") != embedder_name
                or existing.get("model") != model
                or int(existing.get("dim", "0")) != dim
            ):
                raise EmbedderMismatch(
                    f"DB initialized with {existing.get('embedder')} "
                    f"model={existing.get('model')} dim={existing.get('dim')}; "
                    f"requested {embedder_name} model={model} dim={dim}. "
                    f"Re-index required."
                )
            _migrate_schema(conn)
            return
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            [
                ("embedder", embedder_name),
                ("model", model),
                ("dim", str(dim)),
                ("distance", distance),
            ],
        )
        conn.execute(
            "CREATE TABLE entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "text TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "source TEXT NOT NULL, "
            "pinned INTEGER NOT NULL DEFAULT 0, "
            "created_at INTEGER NOT NULL, "
            "last_used_at INTEGER, "
            "use_count INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.execute(
            f"CREATE VIRTUAL TABLE entries_vec USING vec0("
            f"id INTEGER PRIMARY KEY, embedding FLOAT[{dim}])"
        )
        _create_entries_history(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Bring an existing archive DB up to the v0.3.1 schema idempotently."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)").fetchall()}
    if "last_used_at" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN last_used_at INTEGER")
    if "use_count" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0")
    _create_entries_history(conn)
    # DDL auto-commits in sqlite3 legacy mode; this commit ensures a clean close state.
    conn.commit()


def _create_entries_history(conn: sqlite3.Connection) -> None:
    """Create the entries_history table and slug index, idempotent via IF NOT EXISTS."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS entries_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "slug TEXT NOT NULL, "
        "text TEXT NOT NULL, "
        "kind TEXT NOT NULL, "
        "version INTEGER NOT NULL, "
        "original_created_at INTEGER NOT NULL, "
        "superseded_at INTEGER NOT NULL, "
        "provenance TEXT NOT NULL"
        ")"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entries_history_slug "
        "ON entries_history(slug, version)"
    )


def get_meta(db: Path) -> dict[str, str | int]:
    conn = _connect(db)
    try:
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
        out: dict[str, str | int] = {k: v for k, v in rows}
        if "dim" in out:
            out["dim"] = int(out["dim"])
        return out
    finally:
        conn.close()


def assert_compatible(db: Path, *, embedder_name: str, model: str, dim: int) -> None:
    meta = get_meta(db)
    if (
        meta.get("embedder") != embedder_name
        or meta.get("model") != model
        or meta.get("dim") != dim
    ):
        raise EmbedderMismatch(
            f"DB embedder={meta.get('embedder')} model={meta.get('model')} "
            f"dim={meta.get('dim')}; "
            f"requested {embedder_name} model={model} dim={dim}"
        )


def _serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def insert_entry(
    db: Path,
    *,
    text: str,
    kind: str,
    source: str,
    pinned: bool,
    embedding: list[float],
    created_at: int | None = None,
) -> int:
    conn = _connect(db)
    try:
        ts = created_at if created_at is not None else int(time.time())
        # last_used_at/use_count omitted; DB defaults (NULL/0); written by reinforce()
        cur = conn.execute(
            "INSERT INTO entries(text, kind, source, pinned, created_at) VALUES (?, ?, ?, ?, ?)",
            (text, kind, source, int(pinned), ts),
        )
        rowid = cur.lastrowid
        assert rowid is not None
        conn.execute(
            "INSERT INTO entries_vec(id, embedding) VALUES (?, ?)",
            (rowid, _serialize(embedding)),
        )
        conn.commit()
        return rowid
    finally:
        conn.close()


def search(db: Path, *, query_embedding: list[float], top_k: int) -> list[Hit]:
    conn = _connect(db)
    try:
        rows = conn.execute(
            "SELECT e.id, e.text, e.kind, e.source, e.pinned, e.created_at, "
            "e.last_used_at, e.use_count, v.distance "
            "FROM entries_vec v JOIN entries e ON e.id = v.id "
            "WHERE v.embedding MATCH ? AND k = ? "
            "ORDER BY v.distance",
            (_serialize(query_embedding), top_k),
        ).fetchall()
        return [
            Hit(id=r[0], text=r[1], kind=r[2], source=r[3], pinned=bool(r[4]),
                created_at=r[5], last_used_at=r[6], use_count=r[7], distance=r[8])
            for r in rows
        ]
    finally:
        conn.close()


def nearest(db: Path, *, query_embedding: list[float], source_prefix: str) -> Hit | None:
    """Top-1 entry whose source starts with the given prefix (e.g., 'md:')."""
    conn = _connect(db)
    try:
        rows = conn.execute(
            "SELECT e.id, e.text, e.kind, e.source, e.pinned, e.created_at, "
            "e.last_used_at, e.use_count, v.distance "
            "FROM entries_vec v JOIN entries e ON e.id = v.id "
            "WHERE v.embedding MATCH ? AND k = ? AND e.source LIKE ? "
            "ORDER BY v.distance LIMIT 1",
            (_serialize(query_embedding), 50, f"{source_prefix}%"),
        ).fetchall()
        if not rows:
            return None
        r = rows[0]
        return Hit(id=r[0], text=r[1], kind=r[2], source=r[3], pinned=bool(r[4]),
                   created_at=r[5], last_used_at=r[6], use_count=r[7], distance=r[8])
    finally:
        conn.close()


def set_pinned(db: Path, *, row_id: int, pinned: bool) -> int:
    """Set the pinned flag on the entry with id=row_id. Returns rows affected (0 or 1)."""
    conn = _connect(db)
    try:
        cur = conn.execute(
            "UPDATE entries SET pinned = ? WHERE id = ?",
            (int(pinned), row_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def set_pinned_by_slug(db: Path, *, slug: str, pinned: bool) -> int:
    """Set pinned on every row whose source is 'md:<slug>'. Returns rows affected."""
    conn = _connect(db)
    try:
        cur = conn.execute(
            "UPDATE entries SET pinned = ? WHERE source = ?",
            (int(pinned), f"md:{slug}"),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_by_slug(db: Path, *, slug: str) -> int:
    """Delete every row whose source is 'md:<slug>' from entries + entries_vec.
    Returns rows removed."""
    conn = _connect(db)
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM entries WHERE source = ?", (f"md:{slug}",)
        ).fetchall()]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM entries WHERE id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM entries_vec WHERE id IN ({placeholders})", ids)
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def reinforce(db: Path, *, ids: list[int], now: int | None = None) -> int:
    """Bump use_count and set last_used_at for each id. Returns rows updated.

    Empty `ids` is a no-op. Callers SHOULD pass only the ids they actually
    surfaced to the user — this is the reinforcement signal, not a warm-up.
    """
    if not ids:
        return 0
    ts = now if now is not None else int(time.time())
    conn = _connect(db)
    try:
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"UPDATE entries "
            f"SET use_count = use_count + 1, last_used_at = ? "
            f"WHERE id IN ({placeholders})",
            (ts, *ids),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def prune(db: Path, *, days: int) -> int:
    """Delete unpinned entries older than `days` days. Returns count removed."""
    conn = _connect(db)
    try:
        cutoff = int(time.time()) - days * 86400
        cur = conn.execute(
            "SELECT id FROM entries WHERE pinned = 0 AND created_at < ?",
            (cutoff,),
        )
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM entries WHERE id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM entries_vec WHERE id IN ({placeholders})", ids)
        conn.commit()
        return len(ids)
    finally:
        conn.close()
