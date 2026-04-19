"""Embedder protocol and per-provider profile metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Distance = Literal["l2", "cosine"]


@runtime_checkable
class Embedder(Protocol):
    name: str
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
