"""Ollama /api/chat curator provider.

Uses ``format: "json"`` to constrain small models (gemma3:4b) to valid
JSON output. Returns the raw ``message.content`` string; parsing lives
in ``core/curator.py``.
"""
from __future__ import annotations

import contextlib
import logging
import os

import httpx

LOGGER = logging.getLogger("claude_almanac.curators.ollama")


class OllamaCurator:
    name: str = "ollama"

    def __init__(
        self,
        model: str = "gemma3:4b",
        timeout_s: float = 30.0,
        host: str | None = None,
    ) -> None:
        self.model = model
        self.timeout_s = float(timeout_s)
        self.host = host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        self._client = httpx.Client(timeout=httpx.Timeout(
            connect=5.0, read=float(timeout_s), write=30.0, pool=30.0,
        ))

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_turn},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                # 8k >> largest observed curator payload; prevents mid-JSON truncation.
                "num_predict": 8192,
            },
        }
        try:
            resp = self._client.post(f"{self.host}/api/chat", json=payload)
        except httpx.RequestError as e:
            LOGGER.warning("ollama curator %s: %s", type(e).__name__, e)
            return ""
        if resp.status_code != 200:
            LOGGER.warning("ollama curator status %s: %.200s", resp.status_code, resp.text)
            return ""
        try:
            content = resp.json()["message"]["content"]
        except (KeyError, ValueError) as e:
            LOGGER.warning("ollama curator malformed response: %s", e)
            return ""
        if not isinstance(content, str):
            LOGGER.warning("ollama curator: content not a string: %.200r", content)
            return ""
        return content

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()
