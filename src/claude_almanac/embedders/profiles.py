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
        # Typical L2 range on normalized bge-m3 is 0-1.414; 0.1 is ~7% of ceiling.
        rank_band=0.1,
    ),
    # Cloud embedders return normalized vectors; distances are tighter.
    # Values are placeholders pending calibration harness run in Task 19;
    # override in config until calibrated.
    ("openai", "text-embedding-3-small"): EmbedderProfile(
        provider="openai", model="text-embedding-3-small", dim=1536, distance="cosine",
        dedup_distance=0.25,
        # Cosine distance in [0, 2]; 0.05 is a conservative tiebreak width.
        rank_band=0.05,
    ),
    ("voyage", "voyage-3-large"): EmbedderProfile(
        provider="voyage", model="voyage-3-large", dim=1024, distance="cosine",
        dedup_distance=0.22,
        rank_band=0.05,
    ),
    # Qwen3-Embedding: multi-purpose (text + code), officially on Ollama.
    # 0.6B → 1024 dim (drop-in with bge-m3 — same vec-table layout).
    # 4B   → 2560 dim (requires rebuild to swap from bge-m3).
    # 8B   → 4096 dim (ditto).
    # Ollama returns normalized vectors → same "L2 in [0, sqrt(2)]" regime as bge-m3.
    # Thresholds below are bge-m3-inherited defaults; recalibrate via
    # `python -m claude_almanac.embedders.calibrate` on a representative
    # fixture if dedup quality matters.
    ("ollama", "qwen3-embedding:0.6b"): EmbedderProfile(
        provider="ollama", model="qwen3-embedding:0.6b",
        dim=1024, distance="l2",
        dedup_distance=0.5, rank_band=0.1,
    ),
    ("ollama", "qwen3-embedding:4b"): EmbedderProfile(
        provider="ollama", model="qwen3-embedding:4b",
        dim=2560, distance="l2",
        dedup_distance=0.5, rank_band=0.1,
    ),
    ("ollama", "qwen3-embedding:8b"): EmbedderProfile(
        provider="ollama", model="qwen3-embedding:8b",
        dim=4096, distance="l2",
        dedup_distance=0.5, rank_band=0.1,
    ),
}


def get(provider: str, model: str) -> EmbedderProfile:
    key = (provider, model)
    if key not in _PROFILES:
        raise KeyError(f"No profile for {provider}/{model}; configure dedup_distance explicitly")
    return _PROFILES[key]
