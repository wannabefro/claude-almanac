"""UserPromptSubmit handler: embed the prompt and surface top-K memories
from both global and current-project archives."""
from __future__ import annotations

from pathlib import Path

from . import archive, config, paths
from ..embedders import make_embedder
from ..embedders.base import Embedder


def _db_for(directory: Path) -> Path:
    return directory / "archive.db"


def _ensure_db(db: Path, embedder: Embedder, model: str) -> None:
    if not db.exists():
        archive.init(db, embedder_name=embedder.name, model=model,
                     dim=embedder.dim, distance=embedder.distance)
    else:
        archive.assert_compatible(
            db, embedder_name=embedder.name, model=embedder.model,
            dim=embedder.dim,
        )


def format_hits(hits: list[archive.Hit]) -> str:
    if not hits:
        return ""
    lines = ["## Relevant memories (from archive)"]
    for h in hits:
        source = h.source
        tag = f"[{h.kind}]"
        # Grab first line of the body as hook preview; full text follows
        preview = h.text.strip().splitlines()[0] if h.text.strip() else ""
        lines.append(f"- {tag} {source} {preview}")
        remainder = "\n".join(h.text.strip().splitlines()[1:])
        if remainder:
            lines.append(remainder)
    return "\n".join(lines)


def run(prompt: str) -> str:
    """Main entry point. Returns the text to inject as additional context."""
    if not prompt.strip():
        return ""

    cfg = config.load()
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    try:
        [query_vec] = embedder.embed([prompt])
    except Exception:
        # If embedder is unreachable, silently skip injection
        return ""

    paths.ensure_dirs()
    hits: list[archive.Hit] = []
    for scope_dir in (paths.global_memory_dir(), paths.project_memory_dir()):
        scope_dir.mkdir(parents=True, exist_ok=True)
        db = _db_for(scope_dir)
        _ensure_db(db, embedder, cfg.embedder.model)
        hits.extend(
            archive.search(db, query_embedding=query_vec, top_k=cfg.retrieval.top_k)
        )

    hits.sort(key=lambda h: h.distance)
    hits = hits[: cfg.retrieval.top_k]
    return format_hits(hits)
