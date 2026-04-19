"""UserPromptSubmit handler: embed the prompt once and surface top-K memories
plus (optionally) top-K code-index hits, using a single embedder instance.

Code-index integration: gated by `config.retrieval.code_autoinject` AND by
`codeindex.autoinject.should_query(prompt)`. When the per-repo code-index.db
does not exist the code block is silently omitted.
"""
from __future__ import annotations

from pathlib import Path

from claude_almanac.embedders import make_embedder
from claude_almanac.embedders.base import Embedder

from . import archive, config, paths


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


def _codeindex_block(query_vec: list[float]) -> str:
    """Return the optional code-index block to append, or '' if not applicable.

    Separated from run() so tests can patch it independently.
    """
    try:
        from claude_almanac.codeindex import search as ci_search
    except ImportError:
        return ""
    ci_db = paths.project_memory_dir() / "code-index.db"
    if not ci_db.exists():
        return ""
    return ci_search.search_and_format(
        str(ci_db), query_vec=query_vec, sym_k=3, arch_k=2,
    )


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
    out = format_hits(hits)
    if cfg.retrieval.code_autoinject:
        from claude_almanac.codeindex import autoinject
        if autoinject.should_query(prompt):
            code_block = _codeindex_block(query_vec)
            if code_block:
                out = (out + "\n\n" + code_block) if out else code_block
    return out
