"""Codex CLI subprocess curator provider.

Invokes ``codex exec`` non-interactively. Uses the user's logged-in
Codex session (no env-based auth required). Sandboxed read-only so the
agent can't touch the repo.

Like ``claude_cli``, this carries CLI boot overhead (typically
10-30s). Best suited for rollups or other infrequent, high-quality
calls rather than the per-turn curator.
"""
from __future__ import annotations

import logging
import subprocess

LOGGER = logging.getLogger("claude_almanac.curators.codex")


class CodexCurator:
    name: str = "codex"

    def __init__(
        self,
        model: str = "",
        timeout_s: float = 120.0,
        binary: str = "codex",
    ) -> None:
        self.model = model
        self.timeout_s = float(timeout_s)
        self.binary = binary

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        prompt = f"{system_prompt}\n\n{user_turn}" if user_turn else system_prompt
        args = [
            self.binary, "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s", "read-only",
        ]
        if self.model:
            args += ["-m", self.model]
        args.append(prompt)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("codex curator timeout after %ss: %s", self.timeout_s, e)
            return ""
        except FileNotFoundError:
            LOGGER.warning(
                "codex curator: binary %r not found on PATH", self.binary,
            )
            return ""
        if result.returncode != 0:
            LOGGER.warning(
                "codex curator rc=%s stderr=%.200s",
                result.returncode, result.stderr,
            )
            return ""
        return result.stdout
