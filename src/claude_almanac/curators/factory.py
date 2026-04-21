"""Curator provider dispatch based on Config.curator."""
from __future__ import annotations

from claude_almanac.core.config import Config

from .base import Curator

_DEFAULT_TIMEOUT = {
    "ollama": 30,
    "anthropic_sdk": 15,
    # Subprocess-based providers pay CLI boot overhead (~10-45s) per call.
    "claude_cli": 120,
    "codex": 120,
}


def make_curator(cfg: Config) -> Curator:
    cc = cfg.curator
    timeout = cc.timeout_s or _DEFAULT_TIMEOUT.get(cc.provider, 30)
    if cc.provider == "ollama":
        from .ollama import OllamaCurator
        return OllamaCurator(model=cc.model, timeout_s=timeout)
    if cc.provider == "anthropic_sdk":
        from .anthropic_sdk import AnthropicCurator
        return AnthropicCurator(model=cc.model, timeout_s=timeout)
    if cc.provider == "claude_cli":
        from .claude_cli import ClaudeCliCurator
        return ClaudeCliCurator(model=cc.model, timeout_s=timeout)
    if cc.provider == "codex":
        from .codex import CodexCurator
        return CodexCurator(model=cc.model, timeout_s=timeout)
    raise ValueError(f"unknown curator provider: {cc.provider!r}")
