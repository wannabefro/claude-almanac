"""End-to-end: seed entries + a related edge, then confirm the edge surfaces
via _fetch_related_edges and that insert_edge is idempotent on conflict."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_almanac.core import archive, config, paths

pytestmark = pytest.mark.integration


def test_expand_flag_on_surfaces_related_neighbor(
    isolated_data_dir: Path,
) -> None:
    """Seed two thematically-related entries, wire a 'related' edge between them,
    then call _fetch_related_edges and confirm the neighbor surfaces."""
    from claude_almanac.core.retrieve import _fetch_related_edges
    from claude_almanac.edges.store import insert_edge
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile

    cfg = config.default_config()
    profile = get_profile("ollama", "bge-m3")
    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )

    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    # Seed two thematically-related entries so the relationship is realistic.
    foo_id = archive.insert_entry(
        db,
        text="OAuth token refresh rules",
        kind="project",
        source="md:foo_auth",
        pinned=False,
        embedding=embedder.embed(["OAuth token refresh rules"])[0],
    )
    bar_id = archive.insert_entry(
        db,
        text="Session expiry handling",
        kind="project",
        source="md:bar_session",
        pinned=False,
        embedding=embedder.embed(["Session expiry handling"])[0],
    )

    # Attach a 'related' edge foo → bar using a live connection.
    conn = sqlite3.connect(str(db))
    try:
        edge_id = insert_edge(
            conn, foo_id, "entry@project", bar_id, "entry@project",
            "related", "user",
        )
    finally:
        conn.close()

    assert edge_id is not None, "insert_edge should return the edge row id"

    # Verify _fetch_related_edges surfaces bar from foo's perspective.
    conn2 = sqlite3.connect(str(db))
    try:
        related = _fetch_related_edges(conn2, [(foo_id, "entry@project")])
    finally:
        conn2.close()

    assert len(related) == 1, f"expected 1 related edge from foo, got: {related!r}"
    src_id, src_scope, dst_id, dst_scope = related[0]
    assert src_id == foo_id
    assert src_scope == "entry@project"
    assert dst_id == bar_id
    assert dst_scope == "entry@project"


def test_insert_edge_is_idempotent(
    isolated_data_dir: Path,
) -> None:
    """Inserting the same edge twice returns the same id without raising."""
    from claude_almanac.edges.store import insert_edge
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile

    cfg = config.default_config()
    profile = get_profile("ollama", "bge-m3")
    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )

    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    a_id = archive.insert_entry(
        db, text="entry A", kind="project", source="md:a",
        pinned=False,
        embedding=embedder.embed(["entry A"])[0],
    )
    b_id = archive.insert_entry(
        db, text="entry B", kind="project", source="md:b",
        pinned=False,
        embedding=embedder.embed(["entry B"])[0],
    )

    conn = sqlite3.connect(str(db))
    try:
        eid1 = insert_edge(conn, a_id, "entry@project", b_id, "entry@project", "related", "test")
        eid2 = insert_edge(conn, a_id, "entry@project", b_id, "entry@project", "related", "test")
    finally:
        conn.close()

    assert eid1 == eid2, (
        f"idempotent insert should return the same edge id; got {eid1} vs {eid2}"
    )


def test_no_related_edges_returns_empty(
    isolated_data_dir: Path,
) -> None:
    """_fetch_related_edges on an entry with no outgoing edges returns []."""
    from claude_almanac.core.retrieve import _fetch_related_edges
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile

    cfg = config.default_config()
    profile = get_profile("ollama", "bge-m3")
    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )

    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)
    lone_id = archive.insert_entry(
        db, text="lone ranger entry", kind="project", source="md:lone",
        pinned=False,
        embedding=embedder.embed(["lone ranger entry"])[0],
    )

    conn = sqlite3.connect(str(db))
    try:
        related = _fetch_related_edges(conn, [(lone_id, "entry@project")])
    finally:
        conn.close()

    assert related == [], f"expected [] for entry with no edges, got {related!r}"
