"""Fast-mode Q&A: one search_activity call + Haiku synthesis."""
from __future__ import annotations

import subprocess
from textwrap import dedent

from .tools.search_activity import search_activity

_SYSTEM = dedent("""
    You answer questions about recent repo activity and memory changes.
    Cite sources as [repo@sha] (short sha) or [memory:slug].
    Answer concisely. If the excerpts don't support an answer, say so.
""").strip()


def _call_claude(prompt: str, model: str) -> str:
    try:
        out = subprocess.run(
            ["claude", "-p", "--model", model],
            input=prompt, capture_output=True, text=True,
            timeout=45, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("claude timed out after 45s") from e
    if out.returncode != 0:
        raise RuntimeError(f"claude exit {out.returncode}: {out.stderr[:400]}")
    return out.stdout.strip()


def answer_fast(
    *,
    question: str,
    digest_markdown: str,
    date: str,
    model: str = "haiku",
    top_k: int = 8,
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
    prompt = dedent(f"""
        {_SYSTEM}

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
    return _call_claude(prompt, model)
