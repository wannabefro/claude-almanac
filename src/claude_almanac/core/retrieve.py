"""UserPromptSubmit handler: embed the prompt once and surface top-K memories
plus (optionally) top-K code-index hits, using a single embedder instance.

Ranking (v0.3.1): decay-aware banded sort. Within a distance band, higher
decay score ranks earlier. Pinned memories treat score as 1.0. Controlled by
cfg.retrieval.decay.

Code-index integration: gated by `config.retrieval.code_autoinject` AND by
`codeindex.autoinject.should_query(prompt)`. When the per-repo code-index.db
does not exist the code block is silently omitted.
"""
from __future__ import annotations

import time
from pathlib import Path

from claude_almanac.embedders import make_embedder
from claude_almanac.embedders import profiles as embedder_profiles
from claude_almanac.embedders.base import Embedder

from . import archive, config, decay, paths


def _db_for(directory: Path) -> Path:
    return directory / "archive.db"


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
