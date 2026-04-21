"""Graph-walk expansion: 1-hop neighbor fetch + bonus re-scoring.

Pure function taking already-fetched hits + already-fetched related edges.
Retrieval plumbing (fetching edges from DB, fetching neighbor bodies) lives in
`core/retrieve.py` — this module does the math only.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExpandCfg:
    enabled: bool
    bonus: float = 0.25
    hops: int = 1

    def __post_init__(self) -> None:
        if self.hops != 1:
            raise ValueError(f"hops must be 1 in v0.3.2, got {self.hops}")


RelatedEdge = tuple[int, str, int, str]  # (src_id, src_scope, dst_id, dst_scope)


def expand_hits(
    hits: list[Any],
    related_edges: list[RelatedEdge],
    cfg: ExpandCfg,
) -> list[Any]:
    """Return a new list containing the original hits (possibly score-bumped) plus
    neighbor hits surfaced via 1-hop `related` edges, sorted by score desc.

    - Neighbor hits start with a score seeded from the mean score of the hits
      pointing at them, multiplied by `(1 + bonus * normalized_incoming_count)`.
    - Original hits get a small bump proportional to their outgoing `related`
      degree.
    - Edges whose src is not in `hits` are ignored.
    - When `cfg.enabled=False`, returns the input unchanged.
    """
    if not cfg.enabled:
        return hits

    hit_ids = {(h.id, h.scope) for h in hits}

    neighbor_incoming: Counter[tuple[int, str]] = Counter()
    for src_id, src_scope, dst_id, dst_scope in related_edges:
        if (src_id, src_scope) in hit_ids and (dst_id, dst_scope) not in hit_ids:
            neighbor_incoming[(dst_id, dst_scope)] += 1

    if not neighbor_incoming:
        return hits

    max_incoming = max(neighbor_incoming.values())

    # Outgoing degree for bumping original hits.
    outgoing_counts: Counter[tuple[int, str]] = Counter()
    for src_id, src_scope, _, _ in related_edges:
        if (src_id, src_scope) in hit_ids:
            outgoing_counts[(src_id, src_scope)] += 1

    max_outgoing = max(outgoing_counts.values()) if outgoing_counts else 1

    # Seed score per neighbor: max of hits that point at it.
    hits_by_ref = {(h.id, h.scope): h for h in hits}
    neighbor_seed_scores: dict[tuple[int, str], float] = {}
    for (nid, nscope) in neighbor_incoming:
        pointing_hits = [
            hits_by_ref[(src_id, src_scope)]
            for src_id, src_scope, dst_id, dst_scope in related_edges
            if (src_id, src_scope) in hits_by_ref
            and (dst_id, dst_scope) == (nid, nscope)
        ]
        if pointing_hits:
            neighbor_seed_scores[(nid, nscope)] = max(
                h.base_score for h in pointing_hits
            )

    promoted: list[Any] = []
    for h in hits:
        out_count = outgoing_counts.get((h.id, h.scope), 0)
        bonus = cfg.bonus * (out_count / max_outgoing) if max_outgoing > 0 else 0.0
        h.base_score = h.base_score * (1 + bonus)
        promoted.append(h)

    for (nid, nscope), count in neighbor_incoming.items():
        seed = neighbor_seed_scores.get((nid, nscope), 0.0)
        bonus = cfg.bonus * (count / max_incoming)
        promoted.append(_make_neighbor_hit(nid, nscope, seed * (1 + bonus)))

    promoted.sort(key=lambda h: h.base_score, reverse=True)
    return promoted


def _make_neighbor_hit(id: int, scope: str, score: float) -> Any:
    @dataclass
    class _NeighborHit:
        id: int
        scope: str
        base_score: float
        body: str = ""

    return _NeighborHit(id=id, scope=scope, base_score=score)
