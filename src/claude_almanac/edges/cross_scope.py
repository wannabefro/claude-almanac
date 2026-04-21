"""Cross-scope neighbor resolution.

Opens the target-scope archive read-only to materialise the far side of an
edge that crosses DB files. Silently drops edges whose dst can't be
resolved (the target was pruned / rebuilt) — a hygiene concern, not a
correctness error.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CrossScopeHit:
    src_id: int
    src_scope: str
    dst_id: int
    dst_scope: str
    type: str
    body: str         # resolved entry text from src's archive
    slug: str | None  # None for rollups (rollups have no source/slug)


def resolve_cross_scope_neighbors(
    *,
    project_conn: sqlite3.Connection,
    global_conn: sqlite3.Connection | None,
    dst_refs: list[tuple[int, str]],
    type: str,
) -> list[CrossScopeHit]:
    """Find edges in project + global DBs that point at any ref in ``dst_refs``.

    ``dst_refs`` entries are ``(dst_id, dst_scope)``. For each edge found,
    resolves the ``src`` side's body by looking up the matching scope archive.
    Returns one :class:`CrossScopeHit` per resolved edge.

    Silently drops edges whose ``src`` entry no longer exists (e.g. was pruned
    or the archive was rebuilt). A counter in ``/almanac status`` (Task 14)
    will track dangling edges.
    """
    if not dst_refs:
        return []

    results: list[CrossScopeHit] = []
    connections_to_query: list[tuple[sqlite3.Connection, str]] = [
        (project_conn, "project"),
    ]
    if global_conn is not None:
        connections_to_query.append((global_conn, "global"))

    for dst_id, dst_scope in dst_refs:
        for conn, _tag in connections_to_query:
            rows = conn.execute(
                "SELECT src_id, src_scope FROM edges "
                "WHERE dst_id=? AND dst_scope=? AND type=?",
                (dst_id, dst_scope, type),
            ).fetchall()
            for src_id, src_scope in rows:
                body, slug = _lookup_body(
                    project_conn=project_conn,
                    global_conn=global_conn,
                    ref_id=src_id,
                    ref_scope=src_scope,
                )
                if body is None:
                    continue  # unresolvable — silently drop
                results.append(CrossScopeHit(
                    src_id=src_id,
                    src_scope=src_scope,
                    dst_id=dst_id,
                    dst_scope=dst_scope,
                    type=type,
                    body=body,
                    slug=slug,
                ))
    return results


def _lookup_body(
    *,
    project_conn: sqlite3.Connection,
    global_conn: sqlite3.Connection | None,
    ref_id: int,
    ref_scope: str,
) -> tuple[str | None, str | None]:
    """Return ``(body, slug)`` or ``(None, None)`` if the entry is unresolvable.

    The archive ``entries`` table stores the text in the ``text`` column and a
    source identifier in the ``source`` column.  We expose these as ``body``
    and ``slug`` respectively to give callers a uniform surface regardless of
    whether the src is a plain entry or a rollup.
    """
    if ref_scope == "entry@project":
        row = project_conn.execute(
            "SELECT text, source FROM entries WHERE id=?", (ref_id,)
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    if ref_scope == "entry@global" and global_conn is not None:
        row = global_conn.execute(
            "SELECT text, source FROM entries WHERE id=?", (ref_id,)
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    if ref_scope == "rollup@project":
        row = project_conn.execute(
            "SELECT narrative FROM rollups WHERE id=?", (ref_id,)
        ).fetchone()
        return (row[0], None) if row else (None, None)
    return (None, None)
