"""Anthropic SDK curator provider.

Fast-path used when ``ANTHROPIC_API_KEY`` is configured. Sub-second in
practice — the timeout exists only as a network-glitch buffer.
"""
from __future__ import annotations

import logging
import os

import anthropic

LOGGER = logging.getLogger("claude_almanac.curators.anthropic_sdk")


class AnthropicCurator:
    name: str = "anthropic_sdk"

    def __init__(self, model: str, timeout_s: float = 15.0) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set; "
                "anthropic_sdk curator requires an API key in env"
            )
        self.model = model
        self.timeout_s = float(timeout_s)
        self._client = anthropic.Anthropic(api_key=api_key)

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_turn}],
                max_tokens=2048,
                temperature=0,
                timeout=self.timeout_s,
            )
        except anthropic.APIError as e:
            # Covers APIConnectionError, APITimeoutError, RateLimitError,
            # AuthenticationError, BadRequestError, and every other SDK-layer
            # failure. MemoryError / KeyboardInterrupt / bugs propagate.
            LOGGER.warning("anthropic curator %s: %s", type(e).__name__, e)
            return ""
        blocks = getattr(resp, "content", None) or []
        for b in blocks:
            text = getattr(b, "text", None)
            if text:
                if not isinstance(text, str):
                    LOGGER.warning("anthropic curator: text block not string: %.200r", text)
                    return ""
                return text
        LOGGER.warning("anthropic curator: response had no text block")
        return ""
