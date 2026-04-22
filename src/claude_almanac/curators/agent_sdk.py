"""Claude Agent SDK curator provider.

Uses the claude-agent-sdk-python package, which spawns the Claude CLI
subprocess and authenticates via ``CLAUDE_CODE_OAUTH_TOKEN``. Runs
against the configured model (typically Haiku 4.5 for curator
workload).

Latency: fresh subprocess per call (~8-10s warm-start cost on trivial
prompts; larger curator prompts may run 10-30s). Acceptable for the
Stop hook because curation runs in a forked background process; not
suitable for synchronous paths.

Contract: curator providers never raise. On any SDK or transport
failure, return ``""`` so the orchestrator treats it as "no decisions".
"""
from __future__ import annotations

import logging
from typing import Any

import anyio
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

LOGGER = logging.getLogger("claude_almanac.curators.agent_sdk")


class ClaudeAgentSdkCurator:
    name: str = "claude_agent_sdk"

    def __init__(self, model: str, timeout_s: float = 120.0) -> None:
        self.model = model
        self.timeout_s = float(timeout_s)

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        async def _run() -> str:
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                model=self.model,
                max_turns=1,
                allowed_tools=[],  # curator is pure text->text; no tools
            )
            collected = ""
            async for msg in query(prompt=user_turn, options=options):
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            collected = b.text  # keep the last text block
            return collected

        try:
            result: Any = anyio.run(_run)
            return result if isinstance(result, str) else ""
        except Exception as e:
            # Broad catch — curator providers never raise. Matches
            # the AnthropicCurator/ClaudeCliCurator patterns.
            LOGGER.warning("agent_sdk curator %s: %s", type(e).__name__, e)
            return ""
