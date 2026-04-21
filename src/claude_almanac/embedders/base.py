"""Embedder protocol and per-provider profile metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Distance = Literal["l2", "cosine"]


@runtime_checkable
class Embedder(Protocol):
    name: str
    model: str
    dim: int
    distance: Distance

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class EmbedderProfile:
    provider: str
    model: str
    dim: int
    distance: Distance
    dedup_distance: float
    """Calibrated distance threshold below which two vectors are duplicates."""
    rank_band: float = 0.0
    """Distance-band width for decay-aware ranking: hits within the same band
    are tie-broken by decay score. 0.0 disables banding (pure distance sort).
    Rule-of-thumb: roughly 5–15% of the provider's typical distance range.
    """
    min_confidence_distance: float | None = None
    """Code-index low-confidence filter: drop vector-only sym hits whose
    distance exceeds this threshold (v0.3.14). Prevents no-real-match
    queries from surfacing the 3 "nearest" unrelated symbols. ``None``
    disables the filter. Calibrate against a probe fixture: should sit
    just above relevant-query distances and below nonsense-query
    distances. Hits present in the keyword channel bypass the filter.
    """
