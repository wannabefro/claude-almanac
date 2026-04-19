"""Public Q&A entry. Routes `mode` -> fast or deep."""
from __future__ import annotations

from typing import Literal

from .deep import answer_deep
from .fast import answer_fast

Mode = Literal["fast", "deep"]


def answer_question(
    *,
    question: str,
    digest_markdown: str,
    date: str,
    mode: Mode = "fast",
    model: str = "haiku",
) -> str:
    if mode == "fast":
        return answer_fast(
            question=question, digest_markdown=digest_markdown,
            date=date, model=model,
        )
    if mode == "deep":
        return answer_deep(
            question=question, digest_markdown=digest_markdown,
            date=date, model=model,
        ).answer
    raise ValueError(f"invalid mode: {mode!r} (want 'fast' or 'deep')")
