"""Ollama embeddings adapter using /api/embed."""
from __future__ import annotations

import contextlib
import os

import httpx

from .base import Distance


class OllamaEmbedder:
    name: str = "ollama"
    distance: Distance = "l2"  # bge-m3 unnormalized vectors

    def __init__(
        self,
        model: str = "bge-m3",
        dim: int = 1024,
        host: str | None = None,
        timeout: float = 30.0,
    ):
        self.model = model
        self.dim = dim
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._client = httpx.Client(timeout=timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("cannot embed an empty batch")
        resp = self._client.post(
            f"{self.host}/api/embed",
            json={"model": self.model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings: list[list[float]] = data["embeddings"]
        return embeddings

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()
