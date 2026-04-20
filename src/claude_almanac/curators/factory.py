"""Curator provider dispatch based on Config.curator."""
from __future__ import annotations

from claude_almanac.core.config import Config

from .base import Curator

_DEFAULT_TIMEOUT = {"ollama": 30, "anthropic_sdk": 15}


def make_curator(cfg: Config) -> Curator:
    cc = cfg.curator
    timeout = cc.timeout_s or _DEFAULT_TIMEOUT.get(cc.provider, 30)
    if cc.provider == "ollama":
        from .ollama import OllamaCurator
        return OllamaCurator(model=cc.model, timeout_s=timeout)
    if cc.provider == "anthropic_sdk":
        from .anthropic_sdk import AnthropicCurator
        return AnthropicCurator(model=cc.model, timeout_s=timeout)
    raise ValueError(f"unknown curator provider: {cc.provider!r}")
