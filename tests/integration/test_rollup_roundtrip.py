"""End-to-end: real Ollama curator + embedder → RollupGenerator → archive persistence."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from claude_almanac.core import archive, config, paths

pytestmark = pytest.mark.integration


@pytest.fixture
def transcript_fixture(tmp_path: Path) -> Path:
    """A short realistic session transcript for rollup generation."""
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"type":"user","message":{"content":"help me debug test_foo"},"timestamp":1}\n'
        '{"type":"assistant","message":{"content":"reading the test file..."},"timestamp":2}\n'
        '{"type":"user","message":{"content":"option B failed"},"timestamp":3}\n'
        '{"type":"assistant","message":{"content":"let us try option A instead"},"timestamp":4}\n'
        '{"type":"user","message":{"content":"that worked!"},"timestamp":5}\n'
    )
    return path


def test_ollama_real_rollup_roundtrip(
    isolated_data_dir: Path,
    transcript_fixture: Path,
) -> None:
    """RollupGenerator produces a Rollup with a non-empty narrative and it persists to DB."""
    from claude_almanac.curators import make_curator
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile
    from claude_almanac.rollups.generator import RollupGenerator

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
    gen = RollupGenerator(
        curator=make_curator(cfg),
        embedder=embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )

    rollup = gen.generate(
        transcript_path=transcript_fixture,
        session_id="test-session",
        repo_key="test-repo",
        branch=None,
        trigger="explicit",
        min_turns=3,
    )

    # If gemma can't produce a parseable JSON output on this fixture, skip —
    # this is a model-quality probe, not a correctness contract for the LLM.
    if rollup is None:
        pytest.skip("ollama/gemma produced non-JSON or empty narrative on this fixture")

    assert rollup.narrative.strip(), "narrative must not be empty"
    assert isinstance(rollup.decisions, list)
    assert isinstance(rollup.artifacts, dict)
    assert isinstance(rollup.embedding, list)
    assert len(rollup.embedding) == profile.dim

    rid = archive.insert_rollup(
        db,
        session_id=rollup.session_id,
        repo_key=rollup.repo_key,
        branch=rollup.branch,
        started_at=rollup.started_at,
        ended_at=rollup.ended_at,
        turn_count=rollup.turn_count,
        trigger=rollup.trigger,
        narrative=rollup.narrative,
        decisions=json.dumps(rollup.decisions),
        artifacts=json.dumps(rollup.artifacts),
        embedding=rollup.embedding,
    )
    assert rid is not None, "insert_rollup should return a new id"

    # Verify row persisted in the regular rollups table (no vec0 needed).
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT narrative, session_id FROM rollups WHERE id=?", (rid,)
        ).fetchone()
        assert row is not None, f"rollup row {rid} not found after insert"
        assert row[0] == rollup.narrative, "persisted narrative does not match"
        assert row[1] == rollup.session_id
    finally:
        conn.close()

    # Verify vector row was also written — use archive.search_rollups which loads
    # the sqlite_vec extension internally, so we don't have to manage it here.
    hits = archive.search_rollups(db, rollup.embedding, topk=1)
    assert hits, "search_rollups should return at least one hit after insert_rollup"
    assert hits[0][0] == rid, (
        f"expected rollup id {rid} as top hit, got {hits[0][0]}"
    )
