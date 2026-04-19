"""Deep-mode Q&A via claude-agent-sdk + in-process MCP tool server.

Authentication note: uses the local `claude` CLI's OAuth session — no
ANTHROPIC_API_KEY read anywhere. Tools from REGISTRY are wrapped as
claude-agent-sdk @tool functions and exposed through an SDK MCP server;
the Agent SDK drives the tool-use loop.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool as sdk_tool,
)

from .registry import REGISTRY, ToolEntry, auto_discover

# Trigger built-in tool registration once on module import.
auto_discover("claude_almanac.digest.qa.tools")

_SYSTEM = dedent("""
    You answer questions about recent repo activity and memory changes.
    You have access to tools; call them when the digest alone is insufficient.
    Cite sources as [repo@sha] or [memory:slug]. Answer concisely.
    If you cannot answer from the data, say so explicitly.
""").strip()

_MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}

_JSON_TO_PY: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


@dataclass
class DeepResult:
    answer: str
    tool_calls: int
    truncated: bool
    elapsed_s: float


def _wrap_entry_as_sdk_tool(entry: ToolEntry):
    props = entry.schema["input_schema"]["properties"]
    sdk_input_schema = {
        name: _JSON_TO_PY.get(spec.get("type", "string"), str)
        for name, spec in props.items()
    }
    fn = entry.fn

    @sdk_tool(entry.name, entry.description, sdk_input_schema)
    async def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = fn(**args)
            return {
                "content": [
                    {"type": "text", "text": json.dumps(result, default=str)}
                ]
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"tool error: {e}"}],
                "is_error": True,
            }

    return _wrapper


def _build_prompt(question: str, digest_markdown: str, date: str) -> str:
    return dedent(f"""
        Digest for {date}:
        ---
        {digest_markdown}
        ---

        Question: {question}
    """).strip()


async def _run_query(
    *, prompt: str, model: str, max_iterations: int, wall_clock_s: float,
) -> tuple[str, int, bool]:
    sdk_tools = [_wrap_entry_as_sdk_tool(e) for e in REGISTRY.all()]
    server = create_sdk_mcp_server(
        name="digest_qa", version="1.0.0", tools=sdk_tools,
    )
    allowed = [f"mcp__digest_qa__{e.name}" for e in REGISTRY.all()]
    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        mcp_servers={"digest_qa": server},
        allowed_tools=allowed,
        max_turns=max_iterations,
        model=_MODEL_ALIASES.get(model, model),
    )
    answer_parts: list[str] = []
    tool_calls = 0
    truncated = False
    started = time.monotonic()
    async for msg in query(prompt=prompt, options=options):
        if time.monotonic() - started > wall_clock_s:
            truncated = True
            break
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    answer_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_calls += 1
    if tool_calls >= max_iterations:
        truncated = True
    return "".join(answer_parts), tool_calls, truncated


def answer_deep(
    *,
    question: str,
    digest_markdown: str,
    date: str,
    model: str = "haiku",
    max_iterations: int = 5,
    wall_clock_s: float = 30.0,
) -> DeepResult:
    prompt = _build_prompt(question, digest_markdown, date)
    started = time.monotonic()
    answer, tool_calls, truncated = asyncio.run(_run_query(
        prompt=prompt, model=model,
        max_iterations=max_iterations, wall_clock_s=wall_clock_s,
    ))
    elapsed = time.monotonic() - started
    answer = answer.strip() or "(no answer produced)"
    if truncated and "(truncated — exceeded tool budget)" not in answer:
        answer = f"{answer}\n\n(truncated — exceeded tool budget)"
    return DeepResult(
        answer=answer, tool_calls=tool_calls,
        truncated=truncated, elapsed_s=elapsed,
    )
