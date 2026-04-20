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
