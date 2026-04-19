"""OpenAI embeddings adapter. Optional dependency (install extras: [openai])."""
from __future__ import annotations

import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

from .base import Distance


class OpenAIEmbedder:
    name: str = "openai"
    distance: Distance = "cosine"  # text-embedding-3-* returns normalized vectors

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        api_key: str | None = None,
    ):
        if OpenAI is None:
            raise RuntimeError(
                "OpenAI extra not installed. Run: pip install 'claude-almanac[openai]'"
            )
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set and no api_key provided")
        self.model = model
        self.dim = dim
        self._client = OpenAI(api_key=key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("cannot embed an empty batch")
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in resp.data]
