"""Append-only memory versioning: snapshot prior bodies to entries_history,
UPDATE the live entries row in place. One live row per slug invariant.

`list_versions(db, slug)` returns the chain newest-first: the live row appears
first (with provenance = the action that produced it), then historical rows
in descending version order.
"""
from __future__ import annotations

import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import sqlite_vec  # type: ignore[import-untyped]

Provenance = Literal["write_md", "update_md", "dedup", "correct"]


@dataclass
class Version:
    version: int
    text: str
    kind: str
    original_created_at: int
    superseded_at: int | None  # None for the live row
    provenance: str
    is_current: bool


def _connect(db: Path, *, load_vec: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    if load_vec:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    return conn


def _serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def snapshot_then_replace(
    db: Path,
    *,
    scope_dir: Path,
    slug: str,
    new_text: str,
    new_kind: str,
    new_embedding: list[float],
    provenance: Provenance,
) -> None:
    """Write a new version of `slug`:
      - first write for a slug: INSERT into entries (+ entries_vec), no history.
      - identical re-write (new_text == current text): no-op.
      - different body: snapshot current → entries_history, UPDATE live row.

    The current provenance is also stored on the snapshot row so that
    list_versions() can report *why* the prior body was superseded.

    Also writes the md file at `scope_dir / slug`. DB mutations are in one
    transaction; the file write is outside the transaction.
    """
    conn = _connect(db)
    try:
        with conn:
            row = conn.execute(
                "SELECT id, text, kind, created_at FROM entries WHERE source = ?",
                (f"md:{slug}",),
            ).fetchone()
            now = int(time.time())
            if row is not None and row[1] == new_text:
                # Identical re-write. with-block commits the empty txn; skip file write.
                return
            if row is None:
                cur = conn.execute(
                    "INSERT INTO entries(text, kind, source, pinned, created_at, "
                    "last_used_at, use_count) VALUES (?, ?, ?, ?, ?, NULL, 0)",
                    (new_text, new_kind, f"md:{slug}", 1, now),
                )
                rowid = cur.lastrowid
                conn.execute(
                    "INSERT INTO entries_vec(id, embedding) VALUES (?, ?)",
                    (rowid, _serialize(new_embedding)),
                )
            else:
                cur_id, cur_text, cur_kind, cur_created_at = row
                next_version = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM entries_history WHERE slug = ?",
                    (slug,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO entries_history(slug, text, kind, version, "
                    "original_created_at, superseded_at, provenance) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (slug, cur_text, cur_kind, next_version, cur_created_at, now, provenance),
                )
                conn.execute(
                    "UPDATE entries SET text = ?, kind = ?, created_at = ? WHERE id = ?",
                    (new_text, new_kind, now, cur_id),
                )
                conn.execute(
                    "UPDATE entries_vec SET embedding = ? WHERE id = ?",
                    (_serialize(new_embedding), cur_id),
                )
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / slug).write_text(new_text)
    finally:
        conn.close()


def list_versions(db: Path, *, slug: str) -> list[Version]:
    """Return the version chain for `slug`, newest first.

    The live row is first (is_current=True, superseded_at=None). Historical
    rows follow in descending version order. Returns [] if the slug has never
    been written.
    """
    conn = _connect(db, load_vec=False)
    try:
        live = conn.execute(
            "SELECT text, kind, created_at FROM entries WHERE source = ?",
            (f"md:{slug}",),
        ).fetchone()
        hist_rows = conn.execute(
            "SELECT version, text, kind, original_created_at, superseded_at, provenance "
            "FROM entries_history WHERE slug = ? ORDER BY version DESC",
            (slug,),
        ).fetchall()
    finally:
        conn.close()
    result: list[Version] = []
    if live is not None:
        live_text, live_kind, live_created_at = live
        # The provenance of the live row is the provenance of the action that
        # superseded the most recent historical row. If no history, mark as "write_md".
        live_provenance = hist_rows[0][5] if hist_rows else "write_md"
        result.append(Version(
            version=(hist_rows[0][0] + 1) if hist_rows else 1,
            text=live_text, kind=live_kind,
            original_created_at=live_created_at,
            superseded_at=None, provenance=live_provenance, is_current=True,
        ))
    for version, text, kind, orig_created_at, superseded_at, prov in hist_rows:
        result.append(Version(
            version=version, text=text, kind=kind,
            original_created_at=orig_created_at,
            superseded_at=superseded_at, provenance=prov, is_current=False,
        ))
    return result
