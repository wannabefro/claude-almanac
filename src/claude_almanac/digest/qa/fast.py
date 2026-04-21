"""Fast-mode Q&A: one search_activity call + one-shot curator synthesis.

Routes through `curators.factory.make_curator` so Q&A answers honour the
configured provider chain: `cfg.digest.qa_*` > `cfg.digest.narrative_*` >
`cfg.curator`. No direct `claude` binary coupling — works with any provider
(ollama, anthropic_sdk, claude_cli, codex).
"""
from __future__ import annotations

import dataclasses
from textwrap import dedent
from typing import Any

from claude_almanac.core.config import Config
from claude_almanac.core.config import load as load_config
from claude_almanac.curators.base import Curator
from claude_almanac.curators.factory import make_curator

from .tools.search_activity import search_activity

_SYSTEM = dedent("""
    You answer questions about recent repo activity and memory changes.
    Cite sources as [repo@sha] (short sha) or [memory:slug].
    Answer concisely. If the excerpts don't support an answer, say so.
""").strip()


def _qa_curator_cfg(cfg: Config) -> Config:
    """Apply the digest Q&A override chain to cfg.curator.

    Resolution order: qa_provider/qa_model -> narrative_provider/narrative_model
    -> cfg.curator as-is.
    """
    d = cfg.digest
    provider = d.qa_provider or d.narrative_provider
    model = d.qa_model or d.narrative_model
    if provider is None and model is None:
        return cfg
    overrides: dict[str, Any] = {}
    if provider is not None:
        overrides["provider"] = provider
    if model is not None:
        overrides["model"] = model
    return dataclasses.replace(
        cfg, curator=dataclasses.replace(cfg.curator, **overrides),
    )


def answer_fast(
    *,
    question: str,
    digest_markdown: str,
    date: str,
    top_k: int = 8,
    curator: Curator | None = None,
    cfg: Config | None = None,
    # Legacy arg, unused — retained so older callers that pass model="..."
    # don't break. The actual model comes from cfg.digest.qa_model (or the
    # narrative fallback, or cfg.curator.model).
    model: str | None = None,
) -> str:
    hits = search_activity(query=question, top_k=top_k)
    if not hits:
        return (
            "No recent activity found that matches this question. "
            "Try rephrasing or widening the date range."
        )
    excerpts = "\n\n".join(
        f"[{h['repo']}@{h['sha'][:8]}] {h['subject']}\n{h['snippet']}"
        for h in hits
    )
    user_turn = dedent(f"""
        Digest context (already-rendered daily digest for {date}):
        ---
        {digest_markdown}
        ---

        Relevant activity excerpts:
        ---
        {excerpts}
        ---

        Question: {question}
    """).strip()

    if curator is None:
        if cfg is None:
            cfg = load_config()
        curator = make_curator(_qa_curator_cfg(cfg))

    try:
        answer = curator.invoke(_SYSTEM, user_turn).strip()
    except Exception as e:  # providers shouldn't raise, but be defensive
        raise RuntimeError(f"qa provider error: {e}") from e
    if not answer:
        return (
            "The configured Q&A provider returned no answer. Check the "
            "provider's health (e.g. `claude-almanac status`) and retry."
        )
    return answer
