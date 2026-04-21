"""Reciprocal rank fusion for hybrid code retrieval (v0.3.11)."""
from __future__ import annotations

from claude_almanac.contentindex import fuse


def _row(i: int) -> dict[str, object]:
    return {
        "id": i, "kind": "sym", "text": f"t{i}", "file_path": f"f{i}.py",
        "symbol_name": f"S{i}", "module": "m", "line_start": 1, "line_end": 1,
        "commit_sha": "sha1",
    }


def test_single_channel_preserves_order():
    ch = [_row(1), _row(2), _row(3)]
    out = fuse.rrf([ch], top_k=3)
    assert [h["id"] for h in out] == [1, 2, 3]


def test_duplicate_ids_are_summed():
    """A doc at rank 1 in both channels out-ranks docs in only one channel."""
    vec = [_row(1), _row(2), _row(3)]
    kw = [_row(1), _row(4), _row(5)]
    out = fuse.rrf([vec, kw], top_k=3)
    # id=1 appears in both at rank 1 → score = 2 * (1 / (60+1)) ≈ 0.0328
    # others appear in one channel at rank 1-3 → score ≤ 1/61 ≈ 0.0164
    assert out[0]["id"] == 1


def test_rank_1_in_one_channel_beats_rank_3_in_both():
    """A doc ranked 1 in only channel A should beat a doc ranked 3 in BOTH.
    Wait - double check math:
      rank_1_only:  1/(60+1) = 0.01639
      rank_3_both:  2 * 1/(60+3) = 2/63 = 0.03175
    Actually rank-3-in-both DOES beat rank-1-in-one. RRF emphasises consensus.
    Flip the test to assert that behaviour."""
    vec = [_row(1), _row(2), _row(3)]   # doc 1 at rank 1
    kw = [_row(4), _row(5), _row(3)]    # doc 3 also at rank 3 in both channels

    out = fuse.rrf([vec, kw], top_k=3)
    # doc 3 appears at rank 3 in both → 2/63 ≈ 0.0317
    # doc 1 appears at rank 1 in one → 1/61 ≈ 0.0164
    ids = [h["id"] for h in out]
    assert ids[0] == 3


def test_empty_channels_returns_empty():
    assert fuse.rrf([], top_k=5) == []
    assert fuse.rrf([[], []], top_k=5) == []


def test_top_k_limit_respected():
    vec = [_row(i) for i in range(10)]
    out = fuse.rrf([vec], top_k=3)
    assert len(out) == 3


def test_rrf_score_attached_to_results():
    out = fuse.rrf([[_row(1)]], top_k=1)
    assert out[0]["rrf_score"] > 0


def test_custom_k_scales_scores_but_preserves_ordering():
    """Smaller k → steeper rank-decay curve → larger absolute scores.
    Ordering invariants (the useful part of RRF) shouldn't change with k."""
    vec = [_row(1), _row(2), _row(3)]
    kw = [_row(1), _row(4), _row(5)]  # id=1 wins on consensus (rank 1 in both)

    out_k60 = fuse.rrf([vec, kw], top_k=5, k=60)
    out_k1 = fuse.rrf([vec, kw], top_k=5, k=1)

    # Same winner regardless of k
    assert out_k60[0]["id"] == 1
    assert out_k1[0]["id"] == 1
    # k=1 amplifies scores relative to k=60
    assert out_k1[0]["rrf_score"] > out_k60[0]["rrf_score"]
