"""Ollama /api/chat curator provider.

Uses a JSON schema passed via ``format: <schema>`` to grammar-constrain
small models (gemma3:4b, gemma4:e4b) to syntactically-valid JSON with the
expected ``{"decisions": [...]}`` shape. Grammar-constrained decoding on
Ollama ≥ 0.5 enforces at token-gen time, so the model literally cannot
emit unescaped ``"`` inside a string value — fixing a class of curator
failures seen under ``format: "json"`` (which was prompt-only, not
grammar-enforced, on small models).

Returns the raw ``message.content`` string; parsing lives in
``core/curator.py``.
"""
from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger("claude_almanac.curators.ollama")


# Permissive schema: enforce top-level shape + array of objects, but allow
# any keys/types within each decision. This keeps shape tolerance with the
# _parse_decisions handler (which already accepts several decision shapes)
# while closing the unescaped-quote hole that plagued format="json".
_CURATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
            },
        },
    },
    "required": ["decisions"],
}


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
            # v0.3.10: schema-constrained decoding. Grammar enforcement at
            # token-gen prevents malformed JSON (notably unescaped inner
            # quotes) that format="json" permitted on smaller models.
            "format": _CURATOR_SCHEMA,
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
