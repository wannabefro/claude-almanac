"""End-to-end: real Ollama embedder, real archive DB, verify decay-aware ranking
reorders tied-distance hits by reinforcement."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from claude_almanac.core import archive, config, paths, retrieve

pytestmark = pytest.mark.integration


def test_reinforced_outranks_stale_on_tied_distance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    cfg = config.default_config()
    cfg.retrieval.top_k = 2
    cfg.retrieval.decay.enabled = True
    cfg.retrieval.decay.band = 0.3  # wide band to catch near-tied distances
    config.save(cfg)

    from claude_almanac.embedders import make_embedder
    emb = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(db, embedder_name=emb.name, model=emb.model,
                 dim=emb.dim, distance=emb.distance)

    fresh_vec = emb.embed(["decay scoring formula"])[0]
    stale_vec = emb.embed(["decay scoring formula"])[0]
    # Same content on purpose — we want distances close so banding kicks in
    fresh_id = archive.insert_entry(
        db, text="FRESH: the scoring formula",
        kind="note", source="md:fresh.md", pinned=False, embedding=fresh_vec,
    )
    archive.insert_entry(
        db, text="STALE: the scoring formula",
        kind="note", source="md:stale.md", pinned=False,
        embedding=stale_vec, created_at=int(time.time()) - 200 * 86400,
    )
    archive.reinforce(db, ids=[fresh_id], now=int(time.time()))

    out = retrieve.run("decay scoring formula")
    # Extract lines containing FRESH or STALE (the actual hit rows)
    hit_lines = [
        line for line in out.splitlines()
        if "FRESH" in line or "STALE" in line
    ]
    assert len(hit_lines) >= 2, (
        f"expected both hits, got {len(hit_lines)}: {hit_lines!r}"
    )
    assert "FRESH" in hit_lines[0], (
        f"expected FRESH ranked first, got {hit_lines!r}"
    )
