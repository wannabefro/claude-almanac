"""In-place re-embedding for archive + code-index DBs when swapping embedders.

Preserves every row's metadata (id, created_at, use_count, pinned, history,
edges) — only the vector column is recomputed. Handles both dim-same and
dim-change transitions.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("claude_almanac.core.reembed")

_BATCH = 32


def _connect(db: Path) -> sqlite3.Connection:
    import sqlite_vec  # type: ignore[import-untyped]
    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _serialize(vec: list[float]) -> bytes:
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


def _batch(rows: list[Any], size: int) -> list[list[Any]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _rebuild_vec_table(
    conn: sqlite3.Connection, *, table: str, pk: str, new_dim: int,
) -> None:
    """DROP and recreate a vec0 virtual table at the new dim."""
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"CREATE VIRTUAL TABLE {table} USING vec0({pk} INTEGER PRIMARY KEY, "
        f"embedding FLOAT[{new_dim}])",
    )


def reembed_archive(db: Path, *, embedder: Any, model: str) -> tuple[int, int]:
    """Re-embed every entry.text + rollup.narrative in-place.

    Returns (entries_reembedded, rollups_reembedded). Rollups count is 0 when
    the rollups table doesn't exist yet (pre-v0.3.2 archive).
    """
    conn = _connect(db)
    try:
        # Update meta first so the rest of the migration reflects the new
        # embedder. If the user aborts mid-way, a retry picks up cleanly.
        conn.execute(
            "UPDATE meta SET value=? WHERE key='embedder_name'",
            (embedder.name,),
        )
        conn.execute("UPDATE meta SET value=? WHERE key='model'", (model,))
        conn.execute("UPDATE meta SET value=? WHERE key='dim'", (str(embedder.dim),))
        conn.execute(
            "UPDATE meta SET value=? WHERE key='distance'", (embedder.distance,),
        )
        conn.commit()

        _rebuild_vec_table(conn, table="entries_vec", pk="id", new_dim=embedder.dim)
        entries_rows = conn.execute(
            "SELECT id, text FROM entries ORDER BY id",
        ).fetchall()
        n_entries = _reembed_rows(
            conn, rows=entries_rows, vec_table="entries_vec",
            pk_col="id", embedder=embedder,
        )

        rollups_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rollups'",
        ).fetchone() is not None
        n_rollups = 0
        if rollups_exists:
            _rebuild_vec_table(
                conn, table="rollups_vec", pk="rollup_id", new_dim=embedder.dim,
            )
            rollup_rows = conn.execute(
                "SELECT id, narrative FROM rollups ORDER BY id",
            ).fetchall()
            n_rollups = _reembed_rows(
                conn, rows=rollup_rows, vec_table="rollups_vec",
                pk_col="rollup_id", embedder=embedder,
            )

        conn.commit()
        return (n_entries, n_rollups)
    finally:
        conn.close()


def _reembed_rows(
    conn: sqlite3.Connection, *,
    rows: list[tuple[int, str]], vec_table: str, pk_col: str, embedder: Any,
) -> int:
    """Batch-embed texts and upsert into the target vec table."""
    count = 0
    for batch in _batch(rows, _BATCH):
        ids = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        try:
            vecs = embedder.embed(texts)
        except Exception as e:
            LOGGER.warning("reembed batch failed (%d rows): %s", len(batch), e)
            continue
        for rid, vec in zip(ids, vecs, strict=True):
            conn.execute(
                f"INSERT OR REPLACE INTO {vec_table} ({pk_col}, embedding) VALUES (?, ?)",
                (rid, _serialize(vec)),
            )
            count += 1
    return count


def run(dry_run: bool = False) -> int:
    """CLI entry point: migrate every archive on disk to the configured embedder."""
    from claude_almanac.core import config, paths
    from claude_almanac.embedders import make_embedder

    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    dbs: list[Path] = []
    gdb = paths.global_memory_dir() / "archive.db"
    if gdb.exists():
        dbs.append(gdb)
    pdir = paths.projects_memory_dir()
    if pdir.exists():
        for d in pdir.iterdir():
            if d.is_dir():
                pdb = d / "archive.db"
                if pdb.exists():
                    dbs.append(pdb)

    if not dbs:
        print("no archive DBs found")
        return 0

    total_entries = 0
    total_rollups = 0
    for db in dbs:
        # Detect pre-migration dim to decide whether this DB needs work.
        conn = _connect(db)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key='model'",
            ).fetchone()
            current_model = row[0] if row else None
        finally:
            conn.close()
        if current_model == cfg.embedder.model:
            print(f"  {db}: already on {cfg.embedder.model}, skipping")
            continue
        if dry_run:
            print(f"  {db}: would migrate from {current_model} → {cfg.embedder.model}")
            continue
        print(f"migrating {db}: {current_model} → {cfg.embedder.model}")
        n_entries, n_rollups = reembed_archive(
            db, embedder=embedder, model=cfg.embedder.model,
        )
        print(f"  re-embedded {n_entries} entries, {n_rollups} rollups")
        total_entries += n_entries
        total_rollups += n_rollups

    if not dry_run:
        print(
            f"\nmigration complete: {total_entries} entries + "
            f"{total_rollups} rollups re-embedded across {len(dbs)} archive(s)"
        )
    return 0


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    return run(dry_run=dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
