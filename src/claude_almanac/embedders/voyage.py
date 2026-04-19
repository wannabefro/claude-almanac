"""Voyage embeddings adapter. Optional dependency (install extras: [voyage])."""
from __future__ import annotations

import os

try:
    import voyageai
except ImportError:
    voyageai = None  # type: ignore[assignment]

from .base import Distance


class VoyageEmbedder:
    name: str = "voyage"
    distance: Distance = "cosine"

    def __init__(
        self,
        model: str = "voyage-3-large",
        dim: int = 1024,
        api_key: str | None = None,
    ):
        if voyageai is None:
            raise RuntimeError(
                "Voyage extra not installed. Run: pip install 'claude-almanac[voyage]'"
            )
        key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise RuntimeError("VOYAGE_API_KEY not set and no api_key provided")
        self.model = model
        self.dim = dim
        self._client = voyageai.Client(api_key=key)  # type: ignore[attr-defined]

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("cannot embed an empty batch")
        resp = self._client.embed(texts=texts, model=self.model, input_type="document")
        embeddings: list[list[float]] = [
            [float(x) for x in vec] for vec in resp.embeddings
        ]
        return embeddings
