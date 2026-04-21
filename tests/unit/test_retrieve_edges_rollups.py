from dataclasses import dataclass

from claude_almanac.core.retrieve import _filter_superseded, _union_rollups


@dataclass
class FakeHit:
    id: int
    scope: str
    base_score: float


def test_filter_superseded_drops_superseded_dst():
    hits = [FakeHit(1, "entry@project", 0.9), FakeHit(2, "entry@project", 0.7)]
    supersedes_edges = [(10, "entry@project", 2, "entry@project")]
    kept = _filter_superseded(hits, supersedes_edges, enabled=True)
    assert [h.id for h in kept] == [1]


def test_filter_superseded_off_returns_all():
    hits = [FakeHit(1, "entry@project", 0.9), FakeHit(2, "entry@project", 0.7)]
    supersedes_edges = [(10, "entry@project", 2, "entry@project")]
    kept = _filter_superseded(hits, supersedes_edges, enabled=False)
    assert [h.id for h in kept] == [1, 2]


def test_filter_superseded_no_edges_returns_all():
    hits = [FakeHit(1, "entry@project", 0.9)]
    kept = _filter_superseded(hits, [], enabled=True)
    assert [h.id for h in kept] == [1]


def test_union_rollups_merges_when_enabled():
    entry_hits = [FakeHit(1, "entry@project", 0.9)]
    rollup_hits = [FakeHit(5, "rollup@project", 0.7)]
    merged = _union_rollups(entry_hits, rollup_hits, enabled=True)
    assert len(merged) == 2
    # Sorted desc by score — entry (0.9) first, rollup (0.7) second.
    assert [h.id for h in merged] == [1, 5]


def test_union_rollups_off_ignores_rollups():
    entry_hits = [FakeHit(1, "entry@project", 0.9)]
    rollup_hits = [FakeHit(5, "rollup@project", 0.7)]
    merged = _union_rollups(entry_hits, rollup_hits, enabled=False)
    assert merged == entry_hits
