"""Edge CRUD over the `edges` table.

Scope strings are fully-qualified: 'entry@project' | 'entry@global' | 'rollup@project'.
Cross-scope resolution (opening a different archive DB to read the far side) lives
in `cross_scope.py` (added in Task 4). Callers of this module work within a single
connection.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Edge:
    id: int
    src_id: int
    src_scope: str
    dst_id: int
    dst_scope: str
    type: str
    created_at: int
    created_by: str


def insert_edge(
    conn: sqlite3.Connection,
    src_id: int,
    src_scope: str,
    dst_id: int,
    dst_scope: str,
    type: str,
    created_by: str,
    *,
    now: int | None = None,
) -> int:
    """Insert edge; on UNIQUE conflict, return the existing row id. Idempotent."""
    now = now if now is not None else int(time.time())
    conn.execute(
        "INSERT OR IGNORE INTO edges "
        "(src_id, src_scope, dst_id, dst_scope, type, created_at, created_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (src_id, src_scope, dst_id, dst_scope, type, now, created_by),
    )
    row = conn.execute(
        "SELECT id FROM edges WHERE src_id=? AND src_scope=? AND "
        "dst_id=? AND dst_scope=? AND type=?",
        (src_id, src_scope, dst_id, dst_scope, type),
    ).fetchone()
    conn.commit()
    return int(row[0])


def delete_edge(
    conn: sqlite3.Connection,
    src_id: int,
    src_scope: str,
    dst_id: int,
    dst_scope: str,
    type: str,
) -> int:
    cur = conn.execute(
        "DELETE FROM edges WHERE src_id=? AND src_scope=? AND "
        "dst_id=? AND dst_scope=? AND type=?",
        (src_id, src_scope, dst_id, dst_scope, type),
    )
    conn.commit()
    return cur.rowcount


def neighbors(
    conn: sqlite3.Connection,
    src_refs: list[tuple[int, str]],
    *,
    type: str | None = None,
) -> list[Edge]:
    """Outgoing edges from each `(src_id, src_scope)` ref.

    Does NOT cross DB files. Use cross_scope.neighbors for multi-DB queries.
    """
    if not src_refs:
        return []
    placeholders = ",".join(["(?,?)"] * len(src_refs))
    params: list[object] = [v for pair in src_refs for v in pair]
    sql = (
        f"SELECT id, src_id, src_scope, dst_id, dst_scope, type, created_at, created_by"
        f" FROM edges WHERE (src_id, src_scope) IN ({placeholders})"
    )
    if type is not None:
        sql += " AND type = ?"
        params.append(type)
    rows = conn.execute(sql, params).fetchall()
    return [Edge(*r) for r in rows]


def cascade_delete_on_entry(
    conn: sqlite3.Connection, entry_id: int, scope: str
) -> int:
    """Remove every edge where entry appears as src OR dst.

    Called from the pruner when an entry (or rollup) is evicted.
    """
    cur = conn.execute(
        "DELETE FROM edges "
        "WHERE (src_id=? AND src_scope=?) OR (dst_id=? AND dst_scope=?)",
        (entry_id, scope, entry_id, scope),
    )
    conn.commit()
    return cur.rowcount
