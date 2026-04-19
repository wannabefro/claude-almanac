"""Embedder instantiation based on provider + model strings from config."""
from __future__ import annotations

from .base import Embedder
from .profiles import get as get_profile

_KNOWN_PROVIDERS = frozenset({"ollama", "openai", "voyage"})


def make_embedder(provider: str, model: str) -> Embedder:
    """Construct an Embedder instance. Raises ValueError on unknown provider,
    ImportError on missing optional extras, RuntimeError on missing API keys."""
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"unknown embedder provider: {provider}")
    try:
        profile = get_profile(provider, model)
    except KeyError as e:
        raise ValueError(
            f"no profile registered for {provider}/{model}; "
            f"configure thresholds.dedup_distance explicitly"
        ) from e
    if provider == "ollama":
        from .ollama import OllamaEmbedder
        return OllamaEmbedder(model=model, dim=profile.dim)
    if provider == "openai":
        from .openai import OpenAIEmbedder
        return OpenAIEmbedder(model=model, dim=profile.dim)
    if provider == "voyage":
        from .voyage import VoyageEmbedder
        return VoyageEmbedder(model=model, dim=profile.dim)
    # Unreachable due to the guard above, kept for type-narrowing safety.
    raise ValueError(f"unknown embedder provider: {provider}")
