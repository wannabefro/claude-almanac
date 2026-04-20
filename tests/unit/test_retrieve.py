"""retrieve.run() ranking + reinforcement tests with mocked archive/embedder."""
from unittest.mock import patch

import pytest

from claude_almanac.core import archive, retrieve


def _make_hits():
    """Two hits at the same distance, one fresh (high score), one stale (low score)."""
    return [
        archive.Hit(id=1, text="fresh", kind="note", source="md:a.md",
                    pinned=False, created_at=1000, distance=0.3,
                    last_used_at=999, use_count=5),
        archive.Hit(id=2, text="stale", kind="note", source="md:b.md",
                    pinned=False, created_at=0, distance=0.3,
                    last_used_at=None, use_count=0),
    ]


@pytest.fixture
def fake_embedder():
    class E:
        name = "ollama"
        model = "bge-m3"
        dim = 2
        distance = "l2"
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]
    return E()


def test_decay_disabled_preserves_distance_order(tmp_path, monkeypatch, fake_embedder):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.decay.enabled = False
    config.save(cfg)
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", return_value=_make_hits()), \
         patch("claude_almanac.core.archive.reinforce") as mock_reinforce:
        out = retrieve.run("some prompt")
    # With decay disabled, pure distance sort — both tied on 0.3, insertion order kept.
    assert "fresh" in out and "stale" in out
    # reinforcement still fires (it's independent of the ranking knob)
    assert mock_reinforce.called


def test_decay_enabled_ranks_fresh_before_stale_within_band(
    tmp_path, monkeypatch, fake_embedder
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.decay.enabled = True
    cfg.retrieval.decay.band = 0.1  # both hits at 0.3 fall in same band
    config.save(cfg)
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", return_value=_make_hits()), \
         patch("claude_almanac.core.archive.reinforce"):
        out = retrieve.run("some prompt")
    # Fresh (higher score) must appear before stale in the output
    assert out.index("fresh") < out.index("stale")


def test_reinforce_only_surfaced_hits(tmp_path, monkeypatch, fake_embedder):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.top_k = 1  # only one hit actually injected
    config.save(cfg)
    hits = _make_hits()
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", return_value=hits), \
         patch("claude_almanac.core.archive.reinforce") as mock_reinforce:
        retrieve.run("prompt")
    # Verify the TOP hit after ranking was the reinforced id, not some arbitrary one.
    # With decay enabled (default) and both hits at distance=0.3, the fresher
    # use_count=5 hit (id=1) wins the tiebreak over id=2 (never reinforced).
    # reinforce may be called multiple times (once per scope); gather all ids.
    mock_reinforce.assert_called()
    all_called_ids: list[int] = []
    for call in mock_reinforce.call_args_list:
        all_called_ids.extend(call.kwargs["ids"])
    assert all_called_ids == [1], f"expected top hit id=1 reinforced, got {all_called_ids}"


def test_embedder_failure_does_not_reinforce(
    tmp_path, monkeypatch, fake_embedder
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    class Broken:
        name = "ollama"
        model = "bge-m3"
        dim = 2
        distance = "l2"
        def embed(self, texts):
            raise RuntimeError("boom")
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=Broken()), \
         patch("claude_almanac.core.archive.reinforce") as mock_reinforce:
        out = retrieve.run("prompt")
    assert out == ""
    mock_reinforce.assert_not_called()


def test_reinforce_attributes_to_correct_scope_db_despite_id_collision(
    tmp_path, monkeypatch, fake_embedder
):
    """Both scope DBs can have rowid=1 pointing at different entries. Ensure
    reinforcement goes to the right DB via object identity, not hit.id matching.
    """
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.top_k = 2
    config.save(cfg)

    global_hit = archive.Hit(
        id=1, text="global-memory", kind="note", source="md:g.md",
        pinned=False, created_at=1000, distance=0.1,
        last_used_at=None, use_count=0,
    )
    project_hit = archive.Hit(
        id=1, text="project-memory", kind="note", source="md:p.md",
        pinned=False, created_at=1000, distance=0.2,
        last_used_at=None, use_count=0,
    )

    search_call = {"n": 0}
    def fake_search(db, *, query_embedding, top_k):
        search_call["n"] += 1
        return [global_hit] if search_call["n"] == 1 else [project_hit]

    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", side_effect=fake_search), \
         patch("claude_almanac.core.archive.reinforce") as mock_reinforce:
        retrieve.run("prompt")

    # Two reinforce calls, one per DB, each with its own id=1.
    # Collect {db: ids} pairs.
    by_db = {}
    for call in mock_reinforce.call_args_list:
        db_arg = call.args[0] if call.args else call.kwargs.get("db")
        ids = call.kwargs["ids"]
        by_db[db_arg] = ids

    # Exactly two DBs should have received a reinforcement
    assert len(by_db) == 2
    # Each DB got id=[1] (correct for its own scope)
    for db_path, ids in by_db.items():
        assert ids == [1], f"db={db_path} got ids={ids}"


def test_pinned_ranks_above_nonpinned_within_band(
    tmp_path, monkeypatch, fake_embedder
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.decay.band = 0.1
    # Short half-life to ensure non-pinned stale hit's score is clearly < 1.0
    cfg.retrieval.decay.half_life_days = 30
    config.save(cfg)
    hits = [
        # Non-pinned, never reinforced, ancient — score should be << 1.0
        archive.Hit(id=1, text="nonpinned-stale", kind="note", source="md:a.md",
                    pinned=False, created_at=0, distance=0.3,
                    last_used_at=None, use_count=0),
        # Pinned — always score=1.0 regardless of age
        archive.Hit(id=2, text="pinned-ancient", kind="note", source="md:b.md",
                    pinned=True, created_at=0, distance=0.3,
                    last_used_at=None, use_count=0),
    ]
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", return_value=hits), \
         patch("claude_almanac.core.archive.reinforce"):
        out = retrieve.run("prompt")
    # Pinned must rank BEFORE non-pinned-stale (within the same distance band)
    assert out.index("pinned-ancient") < out.index("nonpinned-stale")
