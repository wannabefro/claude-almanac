"""Semantic-dedup pre-check before writing a new md memory file.

Contract: distance < threshold means 'duplicate of existing file'.
Threshold is per-embedder (loaded from profiles or config override).

Calibration note: Ollama bge-m3 now returns unit-normalized vectors;
sqlite-vec L2 distance lives in ~[0, 1.414]. Default dedup threshold
for this profile is 0.5, which catches exact + near-paraphrase dups
while rejecting same-topic pairs (~1.03). Cloud embedders use cosine
distance in ~[0, 2]; see embedders/profiles.py for current thresholds.
"""
from __future__ import annotations

from pathlib import Path

from . import archive


def find_dup_slug(
    *, db: Path, embedding: list[float], threshold: float
) -> tuple[str | None, float | None]:
    """Check for a near-duplicate md-sourced archive entry.

    Returns (slug, distance) if a duplicate exists (distance < threshold),
    otherwise (None, distance) when a nearest exists but is not a duplicate,
    or (None, None) when no md-sourced entries exist yet.
    """
    hit = archive.nearest(db=db, query_embedding=embedding, source_prefix="md:")
    if hit is None:
        return (None, None)
    distance = hit.distance
    if distance >= threshold:
        return (None, distance)
    # source format: "md:<slug>" — strip the prefix
    slug = hit.source.removeprefix("md:")
    return (slug, distance)
