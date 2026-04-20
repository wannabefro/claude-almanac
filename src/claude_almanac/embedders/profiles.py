"""Per-embedder calibration profiles. Thresholds empirically validated.
Users override via config; these are the shipped defaults."""
from __future__ import annotations

from .base import EmbedderProfile

_PROFILES: dict[tuple[str, str], EmbedderProfile] = {
    ("ollama", "bge-m3"): EmbedderProfile(
        provider="ollama", model="bge-m3", dim=1024, distance="l2",
        # Ollama's /api/embed returns *unit-normalized* vectors for bge-m3.
        # L2 distances land in [0, sqrt(2)]. Calibrated pairs:
        #   exact dup:       L2=0.00
        #   paraphrase dup:  L2=~0.67
        #   same-topic:      L2=~1.03
        #   unrelated:       L2=~1.07
        # 0.5 catches exact + near-paraphrase dups, rejects same-topic+.
        #
        # Historical note: pre-0.2.5 profile used 17.0, calibrated against
        # UNnormalized vectors that Ollama used to return. That threshold
        # is unreachable with normalized vectors (max L2 ≈ 1.414), so every
        # dedup check fired and redirected every write to the first
        # existing slug. Fixed in 0.2.5.
        dedup_distance=0.5,
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
