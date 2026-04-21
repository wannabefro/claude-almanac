"""Keyword retrieval channel for the shared content-index engine.

Complements the vector channel in `db.search` by matching query tokens
case-insensitively against `entries.symbol_name`, `entries.file_path`, and the
first line of `entries.text`. Cheap SQLite LIKE scans — no FTS5 migration.

Return shape matches `db.search` (minus `distance`) so `fuse.py` can merge
keyword and vector hits without row-coercion glue.

v0.4: the structural-symbol penalty and single-line-var penalty previously
hardcoded here are now supplied per-kind via
:class:`~claude_almanac.contentindex.scoring.ScoringProfile`. Callers pass
``scoring=CODE_PROFILE`` (from :mod:`claude_almanac.codeindex.scoring`) to
preserve the v0.3.14 behavior; passing ``ScoringProfile()`` (the default
no-op) disables the penalty branches and simplifies the SQL to raw LIKE
counts — useful for ``kind='doc'`` retrieval which has no structural
hijackers.
"""
from __future__ import annotations

import re
import sqlite3

from claude_almanac.contentindex.scoring import ScoringProfile

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
    scoring: ScoringProfile,
) -> list[dict[str, object]]:
    """Return up to `k` rows matching any query token in
    symbol_name / file_path / first-line-of-text.

    Scoring: count of tokens matched across the three columns, tie-broken
    by shorter `file_path`, with a multiplicative penalty (per ``scoring``)
    for rows that match only via file_path and look like structural /
    single-line boilerplate symbols.

    ``scoring`` supplies the penalty rules. The v0.3.14 code-index rules
    live in :data:`claude_almanac.codeindex.scoring.CODE_PROFILE`. Passing
    ``ScoringProfile()`` disables the penalties and collapses the SQL to
    pure LIKE-count scoring.
    """
    tokens = _tokenise(query)
    if not tokens:
        return []

    # If no structural names and both penalties are 1.0, skip the name_hits
    # computation entirely — the CASE expression collapses to a constant
    # 1.0 multiplier, so the extra LIKE scans are pure waste.
    penalties_active = (
        bool(scoring.structural_names)
        or scoring.structural_name_penalty != 1.0
        or scoring.single_line_var_penalty != 1.0
    )

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
        where_any = " OR ".join(where_parts)

        if penalties_active:
            name_sql = " + ".join(name_hit_parts)
            # Build the CASE branches conditionally so an empty
            # structural_names set doesn't emit an invalid ``IN ()``.
            case_branches: list[str] = []
            if scoring.structural_names:
                structural_csv = ", ".join(
                    f"'{n}'" for n in sorted(scoring.structural_names)
                )
                case_branches.append(
                    f"    WHEN name_hits = 0 "
                    f"         AND lower(symbol_name) IN ({structural_csv}) "
                    f"      THEN {scoring.structural_name_penalty} "
                )
            if scoring.single_line_var_penalty != 1.0:
                case_branches.append(
                    f"    WHEN name_hits = 0 "
                    f"         AND (COALESCE(line_end, 0) - COALESCE(line_start, 0)) <= 0 "
                    f"      THEN {scoring.single_line_var_penalty} "
                )
            case_expr = (
                "CASE "
                + "".join(case_branches)
                + "    ELSE 1.0 "
                + "  END"
            )
            sql = (
                f"SELECT id, kind, text, file_path, symbol_name, module, "
                f"line_start, line_end, commit_sha, "
                f"any_hits * ({case_expr}) AS score, "
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
        else:
            # No-op profile: skip the name_hits subquery and the CASE entirely.
            sql = (
                f"SELECT id, kind, text, file_path, symbol_name, module, "
                f"line_start, line_end, commit_sha, "
                f"({any_sql}) AS score, "
                f"length(file_path) AS fp_len "
                f"FROM entries "
                f"WHERE kind = ? AND ({where_any}) "
                f"ORDER BY score DESC, fp_len ASC "
                f"LIMIT ?"
            )
            params = [
                *any_params,
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
