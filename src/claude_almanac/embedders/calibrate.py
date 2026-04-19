"""Calibration helper: embed pairs and report pairwise distances.
Used to derive per-embedder dedup thresholds for the profiles registry."""
from __future__ import annotations

import math

from .base import Embedder


def distances(embedder: Embedder, pairs: list[tuple[str, str]]) -> list[float]:
    flat = [t for pair in pairs for t in pair]
    vecs = embedder.embed(flat)
    out: list[float] = []
    for i, (a, b) in enumerate(pairs):
        va = vecs[2 * i]
        vb = vecs[2 * i + 1]
        if embedder.distance == "l2":
            d = math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb, strict=True)))
        else:  # cosine
            na = math.sqrt(sum(x * x for x in va))
            nb = math.sqrt(sum(x * x for x in vb))
            dot = sum(x * y for x, y in zip(va, vb, strict=True))
            d = 1.0 - dot / (na * nb) if na and nb else 1.0
        out.append(d)
    return out
