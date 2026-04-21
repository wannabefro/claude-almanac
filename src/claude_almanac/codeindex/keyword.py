"""Keyword retrieval channel for the code index (v0.3.11).

Complements the vector channel in `db.search` by matching query tokens
case-insensitively against `entries.symbol_name`, `entries.file_path`, and the
first line of `entries.text`. Cheap SQLite LIKE scans — no FTS5 migration.

Return shape matches `db.search` (minus `distance`) so `fuse.py` can merge
keyword and vector hits without row-coercion glue.
"""
from __future__ import annotations

import re
import sqlite3

_TOKEN_SPLIT = re.compile(r"[\s_\-/.,:;()\[\]{}\"'`]+")
_MIN_TOKEN_LEN = 3


def _tokenise(query: str) -> list[str]:
    """Lowercase, split on word-separator chars, drop tokens below the
    3-char floor to prevent centroid-wide scans."""
    raw = [t for t in _TOKEN_SPLIT.split(query.lower()) if t]
    return [t for t in raw if len(t) >= _MIN_TOKEN_LEN]


def _escape_like(token: str) -> str:
    """Escape SQLite LIKE metacharacters (%, _) and our escape char itself."""
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(
    db_path: str,
    *,
    query: str,
    k: int,
    kind: str = "sym",
) -> list[dict[str, object]]:
    """Return up to `k` rows matching any query token in
    symbol_name / file_path / first-line-of-text.

    Scoring: count of tokens matched across the three columns, tie-broken by
    shorter `file_path` (locality proxy — test/fixture paths tend to be longer
    than domain-code paths once repos grow).
    """
    tokens = _tokenise(query)
    if not tokens:
        return []

    conn = sqlite3.connect(db_path)
    try:
        # Params must be supplied in the SQL-text order of `?`.
        # Order: [score-CASE params (one set of 3 per token, in SELECT),
        #         kind (WHERE),
        #         where-OR params (one set of 3 per token, ORed in WHERE),
        #         k (LIMIT)].
        score_parts: list[str] = []
        where_parts: list[str] = []
        score_params: list[object] = []
        where_params: list[object] = []
        for tok in tokens:
            pattern = f"%{_escape_like(tok)}%"
            score_parts.append(
                "CASE WHEN lower(symbol_name) LIKE ? ESCAPE '\\' "
                "OR lower(file_path) LIKE ? ESCAPE '\\' "
                "OR lower(substr(text,1,200)) LIKE ? ESCAPE '\\' "
                "THEN 1 ELSE 0 END"
            )
            where_parts.append(
                "(lower(symbol_name) LIKE ? ESCAPE '\\' "
                "OR lower(file_path) LIKE ? ESCAPE '\\' "
                "OR lower(substr(text,1,200)) LIKE ? ESCAPE '\\')"
            )
            score_params.extend([pattern, pattern, pattern])
            where_params.extend([pattern, pattern, pattern])

        score_sql = " + ".join(score_parts)
        where_any = " OR ".join(where_parts)

        sql = (
            f"SELECT id, kind, text, file_path, symbol_name, module, "
            f"line_start, line_end, commit_sha, "
            f"({score_sql}) AS score, length(file_path) AS fp_len "
            f"FROM entries "
            f"WHERE kind = ? AND ({where_any}) "
            f"ORDER BY score DESC, fp_len ASC "
            f"LIMIT ?"
        )
        params: list[object] = [*score_params, kind, *where_params, k]
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r[0], "kind": r[1], "text": r[2], "file_path": r[3],
            "symbol_name": r[4], "module": r[5], "line_start": r[6],
            "line_end": r[7], "commit_sha": r[8],
        }
        for r in rows
    ]
