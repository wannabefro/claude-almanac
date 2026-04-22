"""code-index status: DB counts + dirty queue size."""
from __future__ import annotations

import pathlib
import sqlite3

from claude_almanac.contentindex import db as _db
from claude_almanac.core import paths


def _count(db_path: str, kind: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE kind=?", (kind,)
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def main(repo_root: str) -> int:
    repo_root = str(pathlib.Path(repo_root).resolve())
    dbp = paths.project_memory_dir() / "content-index.db"
    if not dbp.exists():
        print(f"no content-index.db at {dbp} — run `claude-almanac content init`")
        return 1
    sym_n = _count(str(dbp), "sym")
    arch_n = _count(str(dbp), "arch")
    dirty = _db.list_dirty(str(dbp))
    last = _db.last_sha(str(dbp)) or "<none>"
    print(f"repo={repo_root}")
    print(f"db={dbp}")
    print(f"last_sha={last}")
    print(f"sym={sym_n}  arch={arch_n}  dirty={len(dirty)}")
    for module, sha in dirty:
        print(f"  dirty: {module} (sha={sha[:8]})")
    return 0
