"""sqlite-vec-backed content-index store.

Path-agnostic engine: the caller supplies ``db_path`` on every entry point.
All callers now use ``paths.project_memory_dir() / 'content-index.db'`` —
the schema is shared across codeindex (kind='sym', 'arch') and documents
(kind='doc') rows; ``kind`` distinguishes them.

Schema:
  entries(id, kind, text, file_path, symbol_name, module, line_start, line_end,
          commit_sha, created_at)
  entries_vec(rowid -> embedding FLOAT[<dim>])
  modules_dirty(module -> marked_sha, marked_at)
Unique keys:
  - (file_path, symbol_name) for kind='sym'
  - (file_path, line_start)  for kind='doc'
  - (module)                 for kind='arch'
"""
from __future__ import annotations

import sqlite3
import struct
from datetime import UTC, datetime

import sqlite_vec  # type: ignore[import-untyped]


def _open(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def init(db_path: str, *, dim: int) -> None:
    conn = _open(db_path)
    try:
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS entries (
              id          INTEGER PRIMARY KEY,
              kind        TEXT NOT NULL,
              text        TEXT NOT NULL,
              file_path   TEXT,
              symbol_name TEXT,
              module      TEXT NOT NULL,
              line_start  INTEGER,
              line_end    INTEGER,
              commit_sha  TEXT NOT NULL,
              created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_entries_file   ON entries(file_path);
            CREATE INDEX IF NOT EXISTS idx_entries_module ON entries(module);
            CREATE INDEX IF NOT EXISTS idx_entries_kind   ON entries(kind);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_sym_key
              ON entries(file_path, symbol_name)
              WHERE kind='sym' AND symbol_name IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_arch_key
              ON entries(module)
              WHERE kind='arch';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_doc_key
              ON entries(file_path, line_start)
              WHERE kind='doc';

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec
              USING vec0(embedding FLOAT[{dim}]);

            CREATE TABLE IF NOT EXISTS modules_dirty (
              module     TEXT PRIMARY KEY,
              marked_sha TEXT NOT NULL,
              marked_at  TEXT NOT NULL
            );
        """)
    finally:
        conn.close()


def upsert(
    db_path: str,
    *,
    kind: str,
    text: str,
    file_path: str | None,
    symbol_name: str | None,
    module: str,
    line_start: int | None,
    line_end: int | None,
    commit_sha: str,
    embedding: list[float],
) -> int:
    """Insert or update an entry. Kind-aware unique-key semantics:
      - ``'sym'``  — unique on (file_path, symbol_name)
      - ``'doc'``  — unique on (file_path, line_start)
      - ``'arch'`` — unique on (module)

    Raw ``SymbolRef.kind`` values like ``'function'`` or ``'class'`` must be
    mapped to ``'sym'`` before calling this; passing them through unchanged is
    the bug this guard exists to surface.
    """
    if kind not in ("sym", "doc", "arch"):
        raise ValueError(f"upsert kind must be 'sym'|'doc'|'arch', got {kind!r}")
    conn = _open(db_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if kind == "sym" and symbol_name is not None:
            row = conn.execute(
                "SELECT id FROM entries WHERE kind='sym' AND file_path=? AND symbol_name=?",
                (file_path, symbol_name),
            ).fetchone()
        elif kind == "doc":
            row = conn.execute(
                "SELECT id FROM entries WHERE kind='doc' AND file_path=? AND line_start=?",
                (file_path, line_start),
            ).fetchone()
        else:  # arch
            row = conn.execute(
                "SELECT id FROM entries WHERE kind='arch' AND module=?",
                (module,),
            ).fetchone()
        if row is not None:
            old_id = row[0]
            conn.execute("DELETE FROM entries_vec WHERE rowid=?", (old_id,))
            conn.execute("DELETE FROM entries WHERE id=?", (old_id,))
        cur = conn.execute(
            "INSERT INTO entries(kind, text, file_path, symbol_name, module,"
            " line_start, line_end, commit_sha, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, text, file_path, symbol_name, module, line_start, line_end,
             commit_sha, _now()),
        )
        new_id = cur.lastrowid
        assert new_id is not None
        conn.execute(
            "INSERT INTO entries_vec(rowid, embedding) VALUES (?, ?)",
            (new_id, _pack(embedding)),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return new_id


def delete_by_file(db_path: str, file_path: str) -> int:
    conn = _open(db_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM entries WHERE file_path=?", (file_path,)
        ).fetchall()]
        for eid in ids:
            conn.execute("DELETE FROM entries_vec WHERE rowid=?", (eid,))
        conn.execute("DELETE FROM entries WHERE file_path=?", (file_path,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return len(ids)


def mark_dirty(db_path: str, *, module: str, sha: str) -> None:
    conn = _open(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO modules_dirty(module, marked_sha, marked_at)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT(module) DO UPDATE SET"
                " marked_sha=excluded.marked_sha, marked_at=excluded.marked_at",
                (module, sha, _now()),
            )
    finally:
        conn.close()


def list_dirty(db_path: str) -> list[tuple[str, str]]:
    conn = _open(db_path)
    try:
        rows = conn.execute(
            "SELECT module, marked_sha FROM modules_dirty ORDER BY marked_at"
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1]) for r in rows]


def clear_dirty(db_path: str, module: str) -> None:
    conn = _open(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM modules_dirty WHERE module=?", (module,))
    finally:
        conn.close()


def last_sha(db_path: str) -> str | None:
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT commit_sha FROM entries ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] is not None else None


def nearest(
    db_path: str,
    *,
    embedding: list[float],
    kind: str | None = None,
    module: str | None = None,
) -> dict[str, object]:
    conn = _open(db_path)
    try:
        k = 20 if (kind is not None or module is not None) else 1
        where = "v.embedding MATCH ? AND k = ?"
        params: list[object] = [_pack(embedding), k]
        if kind is not None:
            where += " AND e.kind = ?"
            params.append(kind)
        if module is not None:
            where += " AND e.module = ?"
            params.append(module)
        rows = conn.execute(
            f"SELECT e.id, e.kind, e.text, e.file_path, e.symbol_name, e.module,"
            f" e.line_start, e.line_end, e.commit_sha, v.distance"
            f" FROM entries_vec v JOIN entries e ON e.id = v.rowid"
            f" WHERE {where} ORDER BY v.distance LIMIT 1",
            params,
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return {}
    r = rows[0]
    return {
        "id": r[0], "kind": r[1], "text": r[2], "file_path": r[3],
        "symbol_name": r[4], "module": r[5], "line_start": r[6],
        "line_end": r[7], "commit_sha": r[8], "distance": r[9],
    }


def search(
    db_path: str,
    *,
    embedding: list[float],
    k: int,
    kind: str | None = None,
    module: str | None = None,
) -> list[dict[str, object]]:
    conn = _open(db_path)
    try:
        fetch_k = max(k * 5, 20) if (kind is not None or module is not None) else k
        where = "v.embedding MATCH ? AND k = ?"
        params: list[object] = [_pack(embedding), fetch_k]
        if kind is not None:
            where += " AND e.kind = ?"
            params.append(kind)
        if module is not None:
            where += " AND e.module = ?"
            params.append(module)
        rows = conn.execute(
            f"SELECT e.id, e.kind, e.text, e.file_path, e.symbol_name, e.module,"
            f" e.line_start, e.line_end, e.commit_sha, v.distance"
            f" FROM entries_vec v JOIN entries e ON e.id = v.rowid"
            f" WHERE {where} ORDER BY v.distance LIMIT ?",
            (*params, k),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0], "kind": r[1], "text": r[2], "file_path": r[3],
            "symbol_name": r[4], "module": r[5], "line_start": r[6],
            "line_end": r[7], "commit_sha": r[8], "distance": r[9],
        }
        for r in rows
    ]
