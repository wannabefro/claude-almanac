from dataclasses import dataclass

import pytest

from claude_almanac.edges.expand import ExpandCfg, expand_hits


@dataclass
class FakeHit:
    id: int
    scope: str
    base_score: float
    body: str = ""


def test_expand_disabled_returns_unchanged():
    hits = [FakeHit(1, "entry@project", 0.8), FakeHit(2, "entry@project", 0.7)]
    result = expand_hits(hits, related_edges=[], cfg=ExpandCfg(enabled=False))
    assert result is hits or result == hits


def test_empty_edges_returns_unchanged():
    hits = [FakeHit(1, "entry@project", 0.8)]
    result = expand_hits(hits, related_edges=[], cfg=ExpandCfg(enabled=True, bonus=0.25, hops=1))
    assert [h.id for h in result] == [1]


def test_expand_adds_neighbor_hits_with_bonus():
    hits = [FakeHit(1, "entry@project", 0.8), FakeHit(2, "entry@project", 0.5)]
    edges = [
        (1, "entry@project", 3, "entry@project"),
        (1, "entry@project", 4, "entry@project"),
        (2, "entry@project", 3, "entry@project"),
    ]
    result = expand_hits(hits, related_edges=edges, cfg=ExpandCfg(enabled=True, bonus=0.25, hops=1))
    ids = {h.id for h in result}
    assert {1, 2, 3, 4} <= ids  # both seed hits + both neighbors present
    # Neighbor 3 is pointed at by 2 seed hits, neighbor 4 by 1. Expect 3 to outrank 4.
    s3 = next(h.base_score for h in result if h.id == 3)
    s4 = next(h.base_score for h in result if h.id == 4)
    assert s3 > s4


def test_expand_sorts_result_by_score_desc():
    hits = [FakeHit(1, "entry@project", 0.9), FakeHit(2, "entry@project", 0.4)]
    edges = [(1, "entry@project", 3, "entry@project")]
    result = expand_hits(hits, related_edges=edges, cfg=ExpandCfg(enabled=True, bonus=0.25, hops=1))
    scores = [h.base_score for h in result]
    assert scores == sorted(scores, reverse=True)


def test_expand_hops_gt_1_raises_in_cfg():
    with pytest.raises(ValueError):
        ExpandCfg(enabled=True, bonus=0.25, hops=2)


def test_expand_ignores_edges_from_non_hit_src():
    hits = [FakeHit(1, "entry@project", 0.8)]
    edges = [(99, "entry@project", 100, "entry@project")]  # src is not a hit
    result = expand_hits(hits, related_edges=edges, cfg=ExpandCfg(enabled=True, bonus=0.25, hops=1))
    # Only original hit remains; the unrelated edge is ignored.
    assert [h.id for h in result] == [1]
