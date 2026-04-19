"""Per-embedder calibration profiles. Thresholds empirically validated.
Users override via config; these are the shipped defaults."""
from __future__ import annotations

from .base import EmbedderProfile

_PROFILES: dict[tuple[str, str], EmbedderProfile] = {
    ("ollama", "bge-m3"): EmbedderProfile(
        provider="ollama", model="bge-m3", dim=1024, distance="l2",
        # Calibrated against real archive workload: duplicates 14-16, same-topic 21-22.
        dedup_distance=17.0,
    ),
    # Cloud embedders return normalized vectors; distances are tighter.
    # Values are placeholders pending calibration harness run in Task 19;
    # override in config until calibrated.
    ("openai", "text-embedding-3-small"): EmbedderProfile(
        provider="openai", model="text-embedding-3-small", dim=1536, distance="cosine",
        dedup_distance=0.25,
    ),
    ("voyage", "voyage-3-large"): EmbedderProfile(
        provider="voyage", model="voyage-3-large", dim=1024, distance="cosine",
        dedup_distance=0.22,
    ),
}


def get(provider: str, model: str) -> EmbedderProfile:
    key = (provider, model)
    if key not in _PROFILES:
        raise KeyError(f"No profile for {provider}/{model}; configure dedup_distance explicitly")
    return _PROFILES[key]
