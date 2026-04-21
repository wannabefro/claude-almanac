"""Keyword retrieval channel for the shared content-index engine.

Complements the vector channel in `db.search` by matching query tokens
case-insensitively against `entries.symbol_name`, `entries.file_path`, and the
first line of `entries.text`. Cheap SQLite LIKE scans — no FTS5 migration.

Return shape matches `db.search` (minus `distance`) so `fuse.py` can merge
keyword and vector hits without row-coercion glue.

v0.3.14: structural-symbol penalty. When no query token matches a row's
``symbol_name``, short module-level hijackers like ``LOGGER`` /
``__init__`` / single-line constants used to tie domain functions and
win by default SQLite row order. A penalty multiplier drops their score
so the behavioral function surfaces first. The rule is name-only
(not body-level) because the extractor occasionally bleeds adjacent
symbol signatures into the ``text`` field, which would otherwise defeat
a body-based check.
"""
from __future__ import annotations

import re
import sqlite3

_TOKEN_SPLIT = re.compile(r"[\s_\-/.,:;()\[\]{}\"'`]+")
_MIN_TOKEN_LEN = 3

# Symbol names whose appearance as a file_path-only match is almost always
# a hijack. Lowercased for comparison against ``lower(symbol_name)``.
_STRUCTURAL_NAMES = (
    "logger",
    "__init__",
    "__all__",
    "__main__",
    "dispatch",
    "main",
)

# Penalty multipliers applied to a row's raw score when the row matched
# ONLY via file_path — i.e., no query token appeared in its symbol_name or
# first-line text.
_STRUCTURAL_NAME_PENALTY = 0.4
_SINGLE_LINE_PENALTY = 0.6


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

    Scoring: count of tokens matched across the three columns, tie-broken
    by shorter `file_path`, with a multiplicative penalty for rows that
    match only via file_path and look like structural/boilerplate symbols
    (see `_STRUCTURAL_NAMES`, `_SINGLE_LINE_PENALTY`).
    """
    tokens = _tokenise(query)
    if not tokens:
        return []

    conn = sqlite3.connect(db_path)
    try:
        # The penalty fires when no query token matched ``symbol_name`` —
        # i.e., the user didn't ask for this symbol by name. We deliberately
        # DON'T check text-body matches here because the extractor sometimes
        # bleeds adjacent symbol signatures into the text field (observed
        # on 2026-04-21: a LOGGER row's text contained the next ``def
        # run_hook(...):``). A body-level check would fire inconsistently;
        # a name-level check expresses the intent cleanly: "structural
        # symbols like LOGGER / __init__ / dispatch / main don't surface
        # unless the query explicitly names them."
        any_hit_parts: list[str] = []
        name_hit_parts: list[str] = []
        where_parts: list[str] = []
        any_params: list[object] = []
        name_params: list[object] = []
        where_params: list[object] = []
        for tok in tokens:
            pattern = f"%{_escape_like(tok)}%"
            any_hit_parts.append(
                "CASE WHEN lower(symbol_name) LIKE ? ESCAPE '\\' "
                "OR lower(file_path) LIKE ? ESCAPE '\\' "
                "OR lower(substr(text,1,200)) LIKE ? ESCAPE '\\' "
                "THEN 1 ELSE 0 END"
            )
            name_hit_parts.append(
                "CASE WHEN lower(symbol_name) LIKE ? ESCAPE '\\' "
                "THEN 1 ELSE 0 END"
            )
            where_parts.append(
                "(lower(symbol_name) LIKE ? ESCAPE '\\' "
                "OR lower(file_path) LIKE ? ESCAPE '\\' "
                "OR lower(substr(text,1,200)) LIKE ? ESCAPE '\\')"
            )
            any_params.extend([pattern, pattern, pattern])
            name_params.append(pattern)
            where_params.extend([pattern, pattern, pattern])

        any_sql = " + ".join(any_hit_parts)
        name_sql = " + ".join(name_hit_parts)
        where_any = " OR ".join(where_parts)

        structural_csv = ", ".join(f"'{n}'" for n in _STRUCTURAL_NAMES)

        # Compute any_hits + name_hits once per row in a subquery so the
        # outer SELECT can reference them in the score expression without
        # duplicating the LIKE scans. Penalty applies only when no query
        # token matched ``symbol_name`` (name_hits = 0).
        sql = (
            f"SELECT id, kind, text, file_path, symbol_name, module, "
            f"line_start, line_end, commit_sha, "
            f"any_hits * ("
            f"  CASE "
            f"    WHEN name_hits = 0 "
            f"         AND lower(symbol_name) IN ({structural_csv}) "
            f"      THEN {_STRUCTURAL_NAME_PENALTY} "
            f"    WHEN name_hits = 0 "
            f"         AND (COALESCE(line_end, 0) - COALESCE(line_start, 0)) <= 0 "
            f"      THEN {_SINGLE_LINE_PENALTY} "
            f"    ELSE 1.0 "
            f"  END"
            f") AS score, "
            f"length(file_path) AS fp_len "
            f"FROM ( "
            f"  SELECT id, kind, text, file_path, symbol_name, module, "
            f"    line_start, line_end, commit_sha, "
            f"    ({any_sql}) AS any_hits, "
            f"    ({name_sql}) AS name_hits "
            f"  FROM entries "
            f"  WHERE kind = ? AND ({where_any}) "
            f") t "
            f"ORDER BY score DESC, fp_len ASC "
            f"LIMIT ?"
        )
        params: list[object] = [
            *any_params,
            *name_params,
            kind,
            *where_params,
            k,
        ]
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
