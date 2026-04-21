"""UserPromptSubmit handler: embed the prompt once and surface top-K memories
plus (optionally) top-K code-index hits, using a single embedder instance.

Ranking (v0.3.1): decay-aware banded sort. Within a distance band, higher
decay score ranks earlier. Pinned memories treat score as 1.0. Controlled by
cfg.retrieval.decay.

Code-index integration: gated by `config.retrieval.code_autoinject` AND by
`codeindex.autoinject.should_query(prompt)`. When the per-repo code-index.db
does not exist the code block is silently omitted.

v0.3.2 retrieval extensions (all gated, default off unless config adds the
`retrieval.edges` / `retrieval.rollups` sections — see Task 8):
  - skip_superseded: filter out hits that are the dst of a live supersedes edge.
  - expand: graph-walk 1-hop neighbor expansion with bonus re-scoring.
  - rollups.autoinject: union entry hits with top-K rollup vector hits.
"""
from __future__ import annotations

import sqlite3
import struct
import time
from pathlib import Path
from typing import Any

import sqlite_vec  # type: ignore[import-untyped]

from claude_almanac.embedders import make_embedder
from claude_almanac.embedders import profiles as embedder_profiles
from claude_almanac.embedders.base import Embedder

from . import archive, config, decay, paths


def _db_for(directory: Path) -> Path:
    return directory / "archive.db"


def _connect_vec(db: Path) -> sqlite3.Connection:
    """Open a sqlite3 connection with sqlite_vec loaded."""
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _ensure_db(db: Path, embedder: Embedder, model: str) -> None:
    if not db.exists():
        archive.init(db, embedder_name=embedder.name, model=model,
                     dim=embedder.dim, distance=embedder.distance)
    else:
        archive.assert_compatible(
            db, embedder_name=embedder.name, model=embedder.model,
            dim=embedder.dim,
        )


def format_hits(hits: list[archive.Hit]) -> str:
    if not hits:
        return ""
    lines = ["## Relevant memories (from archive)"]
    for h in hits:
        source = h.source
        tag = f"[{h.kind}]"
        preview = h.text.strip().splitlines()[0] if h.text.strip() else ""
        lines.append(f"- {tag} {source} {preview}")
        remainder = "\n".join(h.text.strip().splitlines()[1:])
        if remainder:
            lines.append(remainder)
    return "\n".join(lines)


def _codeindex_block(query_vec: list[float]) -> str:
    try:
        from claude_almanac.codeindex import search as ci_search
    except ImportError:
        return ""
    ci_db = paths.project_memory_dir() / "code-index.db"
    if not ci_db.exists():
        return ""
    return ci_search.search_and_format(
        str(ci_db), query_vec=query_vec, sym_k=3, arch_k=2,
    )


def _resolve_band(cfg_band: float, embedder: Embedder) -> float:
    if cfg_band and cfg_band > 0:
        return cfg_band
    try:
        return embedder_profiles.get(embedder.name, embedder.model).rank_band
    except KeyError:
        return 0.0


def _score_for(hit: archive.Hit, *, now: int, dcfg: config.DecayCfg) -> float:
    if hit.pinned:
        return 1.0
    return decay.decay_score(
        hit.created_at, hit.last_used_at, hit.use_count, now,
        half_life_days=dcfg.half_life_days,
        use_count_exponent=dcfg.use_count_exponent,
    )


def _rank_key(
    hit: archive.Hit, *, now: int, band: float, dcfg: config.DecayCfg,
) -> tuple[float, float]:
    score = _score_for(hit, now=now, dcfg=dcfg)
    banded = round(hit.distance / band) * band if band > 0 else hit.distance
    return (banded, -score)


def run(prompt: str) -> str:
    """Main entry point. Returns the text to inject as additional context."""
    if not prompt.strip():
        return ""

    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    try:
        [query_vec] = embedder.embed([prompt])
    except Exception:
        return ""

    paths.ensure_dirs()
    hits_by_scope: dict[Path, list[archive.Hit]] = {}
    hits: list[archive.Hit] = []
    for scope_dir in (paths.global_memory_dir(), paths.project_memory_dir()):
        scope_dir.mkdir(parents=True, exist_ok=True)
        db = _db_for(scope_dir)
        _ensure_db(db, embedder, cfg.embedder.model)
        scope_hits = archive.search(
            db, query_embedding=query_vec, top_k=cfg.retrieval.top_k,
        )
        hits_by_scope[db] = scope_hits
        hits.extend(scope_hits)

    # --- v0.3.2 retrieval extensions (all gated) ---
    # cfg.retrieval.edges / cfg.retrieval.rollups may not exist on v0.3.1 configs;
    # AttributeError fallback treats all new features as off.

    # 1. Skip superseded: drop hits that are the dst of a live supersedes edge.
    try:
        skip_superseded_flag: bool = cfg.retrieval.edges.skip_superseded  # type: ignore[attr-defined]
    except AttributeError:
        skip_superseded_flag = False
    if skip_superseded_flag and hits:
        refs = [(h.id, _scope_of(h)) for h in hits]
        # Use the project archive DB for edge lookups (edges live there).
        _proj_db = _db_for(paths.project_memory_dir())
        if _proj_db.exists():
            _conn_skip = _connect_vec(_proj_db)
            try:
                sup_edges = _fetch_supersedes_edges(_conn_skip, refs)
            finally:
                _conn_skip.close()
            hits = _filter_superseded(hits, sup_edges, enabled=True)

    # 2. Graph-walk expansion (1-hop related edges, bonus re-scoring).
    # Note: archive.Hit objects don't carry .scope or .base_score natively;
    # expand_hits relies on both. This path is default-off and only activates
    # once Task 8 adds edges.expand to config. When active, ensure hits have
    # been augmented with those fields before calling expand_hits.
    try:
        expand_flag: bool = cfg.retrieval.edges.expand  # type: ignore[attr-defined]
        expand_bonus: float = cfg.retrieval.edges.expand_bonus  # type: ignore[attr-defined]
        expand_hops: int = cfg.retrieval.edges.expand_hops  # type: ignore[attr-defined]
    except AttributeError:
        expand_flag = False
    if expand_flag and hits:
        from claude_almanac.edges.expand import ExpandCfg
        from claude_almanac.edges.expand import expand_hits as _expand_hits_fn
        refs = [(h.id, _scope_of(h)) for h in hits]
        _proj_db = _db_for(paths.project_memory_dir())
        if _proj_db.exists():
            _conn_exp = _connect_vec(_proj_db)
            try:
                related = _fetch_related_edges(_conn_exp, refs)
            finally:
                _conn_exp.close()
            hits = _expand_hits_fn(
                hits, related,
                ExpandCfg(enabled=True, bonus=expand_bonus, hops=expand_hops),
            )

    # 3. Rollups union: merge entry hits with top-K rollup vector hits.
    try:
        rollup_ai: bool = cfg.retrieval.rollups.autoinject  # type: ignore[attr-defined]
        rollup_topk: int = cfg.retrieval.rollups.topk  # type: ignore[attr-defined]
        rollup_cutoff: float = cfg.retrieval.rollups.distance_cutoff  # type: ignore[attr-defined]
    except AttributeError:
        rollup_ai = False
    if rollup_ai:
        _proj_db = _db_for(paths.project_memory_dir())
        if _proj_db.exists():
            _conn_roll = _connect_vec(_proj_db)
            try:
                rollup_hits = _vector_top_k_rollups(
                    _conn_roll, query_vec,
                    topk=rollup_topk, cutoff=rollup_cutoff,
                )
            finally:
                _conn_roll.close()
            hits = _union_rollups(hits, rollup_hits, enabled=True)

    now = int(time.time())
    dcfg = cfg.retrieval.decay
    if dcfg.enabled:
        band = _resolve_band(dcfg.band, embedder)
        hits.sort(key=lambda h: _rank_key(h, now=now, band=band, dcfg=dcfg))
    else:
        hits.sort(key=lambda h: h.distance)

    hits = hits[: cfg.retrieval.top_k]

    # Map each Hit object (by Python id) to its source DB. Sqlite rowids are
    # per-DB, so we cannot rely on hit.id for attribution — global and project
    # scopes both start their AUTOINCREMENT at 1.
    hit_to_db: dict[int, Path] = {}
    for db, scope_hits in hits_by_scope.items():
        for sh in scope_hits:
            hit_to_db[id(sh)] = db

    # After sort + top_k slice, surface only the ids we actually returned,
    # attributed to the correct DB via object identity.
    surfaced_ids_by_db: dict[Path, list[int]] = {db: [] for db in hits_by_scope}
    for h in hits:
        db = hit_to_db[id(h)]
        surfaced_ids_by_db[db].append(h.id)
    for db, ids in surfaced_ids_by_db.items():
        if ids:
            archive.reinforce(db, ids=ids, now=now)

    out = format_hits(hits)
    if cfg.retrieval.code_autoinject:
        from claude_almanac.codeindex import autoinject
        if autoinject.should_query(prompt):
            code_block = _codeindex_block(query_vec)
            if code_block:
                out = (out + "\n\n" + code_block) if out else code_block
    return out


# ---------------------------------------------------------------------------
# v0.3.2 pure helper functions (gated via run() callers)
# ---------------------------------------------------------------------------

def _scope_of(h: Any) -> str:
    """Return the scope of a hit.

    Entry Hits from the archive don't carry a scope field; they're always
    ``entry@project`` in current code. Rollup hits have an explicit ``scope``
    attribute. Synthesize appropriately.
    """
    return getattr(h, "scope", "entry@project")


def _filter_superseded(
    hits: list[Any],
    supersedes_edges: list[tuple[int, str, int, str]],
    *,
    enabled: bool,
) -> list[Any]:
    """Drop hits whose (id, scope) is the dst of a supersedes edge.

    When disabled, returns hits unchanged.
    """
    if not enabled:
        return hits
    superseded = {(dst_id, dst_scope) for _, _, dst_id, dst_scope in supersedes_edges}
    return [h for h in hits if (h.id, _scope_of(h)) not in superseded]


def _union_rollups(
    entry_hits: list[Any],
    rollup_hits: list[Any],
    *,
    enabled: bool,
) -> list[Any]:
    """Merge entry + rollup hits, sorted by base_score desc. Disabled → entries only."""
    if not enabled:
        return entry_hits
    merged = list(entry_hits) + list(rollup_hits)
    merged.sort(key=lambda h: h.base_score, reverse=True)
    return merged


# ---------------------------------------------------------------------------
# v0.3.2 DB helpers (private — called from run() under feature flags)
# ---------------------------------------------------------------------------

def _fetch_supersedes_edges(
    conn: sqlite3.Connection,
    refs: list[tuple[int, str]],
) -> list[tuple[int, str, int, str]]:
    """Return (src_id, src_scope, dst_id, dst_scope) for every supersedes edge
    where dst is in refs. Single-scope lookup (cross-scope handled elsewhere)."""
    if not refs:
        return []
    placeholders = ",".join(["(?,?)"] * len(refs))
    params = [v for pair in refs for v in pair]
    rows = conn.execute(
        f"SELECT src_id, src_scope, dst_id, dst_scope FROM edges "
        f"WHERE type='supersedes' AND (dst_id, dst_scope) IN ({placeholders})",
        params,
    ).fetchall()
    return [(int(r[0]), r[1], int(r[2]), r[3]) for r in rows]


def _fetch_related_edges(
    conn: sqlite3.Connection,
    refs: list[tuple[int, str]],
) -> list[tuple[int, str, int, str]]:
    """Return (src_id, src_scope, dst_id, dst_scope) for every related edge
    whose src is in refs."""
    if not refs:
        return []
    placeholders = ",".join(["(?,?)"] * len(refs))
    params = [v for pair in refs for v in pair]
    rows = conn.execute(
        f"SELECT src_id, src_scope, dst_id, dst_scope FROM edges "
        f"WHERE type='related' AND (src_id, src_scope) IN ({placeholders})",
        params,
    ).fetchall()
    return [(int(r[0]), r[1], int(r[2]), r[3]) for r in rows]


def _vector_top_k_rollups(
    conn: sqlite3.Connection,
    query_vec: list[float],
    *,
    topk: int,
    cutoff: float,
) -> list[Any]:
    """Top-k rollups by vector distance. Returns objects with (id, scope,
    base_score, narrative) fields so they merge cleanly with entry hits via
    _union_rollups (which ranks by base_score)."""
    from dataclasses import dataclass

    @dataclass
    class _RollupHit:
        id: int
        scope: str
        base_score: float
        narrative: str

    # Match the same serialization style used by archive.search (struct.pack float32).
    vec_bytes = struct.pack(f"{len(query_vec)}f", *query_vec)
    rows = conn.execute(
        "SELECT r.id, v.distance, r.narrative "
        "FROM rollups r JOIN rollups_vec v ON r.id = v.rollup_id "
        "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
        (vec_bytes, topk),
    ).fetchall()
    result: list[Any] = []
    for rid, dist, narrative in rows:
        if dist > cutoff:
            continue
        # Convert distance to a score comparable to entry-hit decay scores:
        # best possible distance (0) → score 1.0; cutoff distance → score 0.0.
        score = max(0.0, 1.0 - float(dist) / cutoff)
        result.append(_RollupHit(
            id=int(rid),
            scope="rollup@project",
            base_score=score,
            narrative=str(narrative),
        ))
    return result
