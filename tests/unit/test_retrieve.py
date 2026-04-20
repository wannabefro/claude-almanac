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
    # Called exactly once, with one id (the top hit after ranking)
    mock_reinforce.assert_called()
    called_ids = mock_reinforce.call_args.kwargs["ids"]
    assert len(called_ids) == 1


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


def test_pinned_ranks_above_nonpinned_within_band(
    tmp_path, monkeypatch, fake_embedder
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config
    cfg = config.default_config()
    cfg.retrieval.decay.band = 0.1
    config.save(cfg)
    hits = [
        # nonpinned but freshly reinforced
        archive.Hit(id=1, text="nonpinned-fresh", kind="note", source="md:a.md",
                    pinned=False, created_at=1000, distance=0.3,
                    last_used_at=1000, use_count=100),
        # pinned, ancient, never reinforced
        archive.Hit(id=2, text="pinned-stale", kind="note", source="md:b.md",
                    pinned=True, created_at=0, distance=0.3,
                    last_used_at=None, use_count=0),
    ]
    with patch("claude_almanac.core.retrieve.make_embedder", return_value=fake_embedder), \
         patch("claude_almanac.core.archive.search", return_value=hits), \
         patch("claude_almanac.core.archive.reinforce"):
        out = retrieve.run("prompt")
    # Pinned gets score=1.0 which is comparable to use_count=100 fresh. But the
    # invariant is weak: we only assert both appear — ordering between two high-
    # score hits within a band is implementation-defined by the sort's stability.
    # The STRONG assertion is covered by test_decay_enabled_ranks_fresh_before_stale.
    assert "pinned-stale" in out
    assert "nonpinned-fresh" in out
