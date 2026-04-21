"""Claude CLI subprocess curator provider.

Invokes ``claude -p --model <model> <prompt>`` as a subprocess. Uses the
user's Claude Code OAuth session — no ``ANTHROPIC_API_KEY`` needed.

Trade-off: each invocation eats ~30-45s of CLI boot. Not suitable for
the per-turn curator hot path (where Ollama or the Anthropic SDK are
better choices). Intended primarily for session-grain rollups where
one boot per session is worth it for Haiku-grade output on a machine
without an API key.
"""
from __future__ import annotations

import logging
import subprocess

LOGGER = logging.getLogger("claude_almanac.curators.claude_cli")


class ClaudeCliCurator:
    name: str = "claude_cli"

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        timeout_s: float = 120.0,
        binary: str = "claude",
    ) -> None:
        self.model = model
        self.timeout_s = float(timeout_s)
        self.binary = binary

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        prompt = f"{system_prompt}\n\n{user_turn}" if user_turn else system_prompt
        args = [self.binary, "-p", "--model", self.model, prompt]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("claude_cli curator timeout after %ss: %s", self.timeout_s, e)
            return ""
        except FileNotFoundError:
            LOGGER.warning(
                "claude_cli curator: binary %r not found on PATH",
                self.binary,
            )
            return ""
        if result.returncode != 0:
            LOGGER.warning(
                "claude_cli curator rc=%s stderr=%.200s",
                result.returncode, result.stderr,
            )
            return ""
        return result.stdout
