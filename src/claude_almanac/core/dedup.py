"""Semantic-dedup pre-check before writing a new md memory file.

Contract: distance < threshold means 'duplicate of existing file'.
Threshold is per-embedder (loaded from profiles or config override).

Calibration note: bge-m3 via Ollama returns unnormalized vectors; sqlite-vec
L2 distance lives in ~14-29 range. 17.0 sits between duplicate-ceiling (~16)
and same-topic floor (~21). Cloud embedders use cosine distance and need
their own calibrated threshold.
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
