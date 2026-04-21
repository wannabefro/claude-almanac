"""Reciprocal rank fusion for hybrid code retrieval (v0.3.11).

Merges ranked result lists from independent channels (vector + keyword) into
a single ranking. RRF sums `1/(k + rank)` across channels per doc id, which
requires no per-channel score normalisation — the two channels here produce
values on wildly different scales (L2 distance in ~14–29 for qwen3-embedding
vs integer match-count for keyword), so RRF is a natural fit.

Reference: Cormack, Clarke, Buettcher. "Reciprocal Rank Fusion outperforms
Condorcet and individual rank learning methods." SIGIR '09. Default k=60 is
the canonical constant from that paper.
"""
from __future__ import annotations

from typing import Any

DEFAULT_K = 60


def rrf(
    channels: list[list[dict[str, Any]]],
    *,
    top_k: int,
    k: int = DEFAULT_K,
) -> list[dict[str, Any]]:
    """Fuse ranked channels. Each channel is a list of hit dicts ordered by
    that channel's own score; RRF does not inspect per-channel scores.

    Dedupes by `id`. Returns up to `top_k` hits sorted by summed RRF score
    descending, with `rrf_score` attached to each returned dict.
    """
    if not channels or top_k <= 0:
        return []

    scores: dict[int, float] = {}
    first_seen: dict[int, dict[str, Any]] = {}
    for ch in channels:
        for rank, hit in enumerate(ch, start=1):
            hit_id = int(hit["id"])
            scores[hit_id] = scores.get(hit_id, 0.0) + 1.0 / (k + rank)
            # Preserve the full row payload from the first time we see the id.
            # Channels return slightly different columns (vector has `distance`,
            # keyword does not) so we prefer the vector row when available.
            if hit_id not in first_seen or "distance" in hit:
                first_seen[hit_id] = hit

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: list[dict[str, Any]] = []
    for hit_id, score in ranked[:top_k]:
        row = dict(first_seen[hit_id])
        row["rrf_score"] = score
        out.append(row)
    return out
