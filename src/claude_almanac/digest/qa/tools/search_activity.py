"""search_activity — vector search over activity.db with optional filters."""
from __future__ import annotations

import sqlite3
import struct
from typing import Any

import sqlite_vec  # type: ignore[import-untyped]

from claude_almanac.core import archive, paths
from claude_almanac.core import config as core_config
from claude_almanac.digest.qa.registry import tool
from claude_almanac.embedders import make_embedder


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


@tool(
    "search_activity",
    "Semantic search over indexed repo activity (commits from activity.db). "
    "Use to answer 'what changed around <topic>?' questions.",
)
def search_activity(
    query: str,
    repo: str | None = None,
    since: str | None = None,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Return [{repo, sha, subject, snippet, distance}, ...]."""
    db = paths.data_dir() / "activity.db"
    if not db.exists():
        return []
    cfg = core_config.load()
    try:
        embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
        archive.assert_compatible(
            db, embedder_name=embedder.name, model=embedder.model, dim=embedder.dim,
        )
        [vec] = embedder.embed([query])
    except archive.EmbedderMismatch:
        raise  # don't mask a real corruption signal
    except Exception:
        return []
    conn = sqlite3.connect(str(db), timeout=5.0)
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        k = top_k * 4
        where = ["v.embedding MATCH ?", "k = ?"]
        params: list[Any] = [_pack(vec), k]
        if repo:
            where.append("am.repo = ?")
            params.append(repo)
        if since:
            where.append("m.created_at >= ?")
            params.append(since)
        sql = f"""
            SELECT am.repo, am.sha, m.text, v.distance
            FROM memories_vec v
            JOIN memories m ON m.id = v.rowid
            JOIN activity_meta am ON am.id = v.rowid
            WHERE {" AND ".join(where)}
            ORDER BY v.distance
            LIMIT {top_k}
        """
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [
        {
            "repo": r,
            "sha": s,
            "subject": t.split("\n", 1)[0][:200],
            "snippet": t[:1000],
            "distance": d,
        }
        for r, s, t, d in rows
    ]
