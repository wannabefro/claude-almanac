"""Symbol extractor: public symbols only, batch-embed per file.

Design trade-off (inherited from memory-tools/code_index_sym.py): we skip
de-facto-public detection (private symbols with >=3 callers). That removes
the Serena round-trip per private symbol, which was the bottleneck at scale
(17k+ Python files). Lost recall is small because private-but-popular symbols
are rare.

Embedding uses the Plan 1 Embedder protocol; callers pass an instance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_almanac import core  # noqa: F401  (kept for future cross-package imports)
from claude_almanac.codeindex.extractors import extract_symbols
from claude_almanac.codeindex.log import emit
from claude_almanac.contentindex import db as _db
from claude_almanac.core import paths

SNIPPET_CHARS = 120
MAX_CALLSITES = 3

_CODE_EXTS = {"py", "ts", "tsx", "js", "jsx", "go", "java", "rs"}


def compose_text(
    signature: str,
    references: list[Any],
    *,
    file_rel: str = "",
    module: str = "",
    kind: str = "",
    name: str = "",
) -> str:
    """Build the text embedded into entries_vec for one symbol.

    v0.3.8: includes file path + module + kind + name as a header line so
    queries like "archive migration schema" land on `ensure_schema` in
    `core/archive.py` via path-token overlap, not just the bare signature.
    General-text embedders (bge-m3, nomic-embed-text) benefit disproportionately
    from this enrichment because they're not code-specialized — they ride on
    natural-language tokens, and paths are the richest semantic anchor in the
    symbol surface.
    """
    header_parts = [p for p in (file_rel, kind and f"[{kind}]", name) if p]
    lines: list[str] = []
    if header_parts:
        lines.append("// " + "  ".join(header_parts))
    lines.append(signature)
    if references:
        lines.append("")
        lines.append("// used in:")
        for ref in references[:MAX_CALLSITES]:
            snippet = ref.snippet[:SNIPPET_CHARS]
            lines.append(f"{ref.file_rel}:{ref.line}  {snippet}")
    return "\n".join(lines)


def extract_file(*, db_path: str, repo_root: str, module: str, file_abs: str,
                 commit_sha: str, embedder: Any) -> int:
    """Extract public symbols from one file; upsert each. Returns count written."""
    log_path = paths.logs_dir() / "code-index.log"
    ext = Path(file_abs).suffix.lstrip(".").lower()
    if ext not in _CODE_EXTS:
        return 0
    file_rel = str(Path(file_abs).relative_to(repo_root))
    syms = extract_symbols(file_abs, file_rel, repo_root)
    if not syms:
        return 0
    public_syms = [s for s in syms if s.visibility == "public"]
    if not public_syms:
        return 0
    texts = [
        compose_text(
            s.signature, [],
            file_rel=file_rel, module=module, kind=s.kind, name=s.name,
        )
        for s in public_syms
    ]
    try:
        vecs = embedder.embed(texts)
    except Exception as e:
        emit(log_path, component="code-index", level="error",
             event="sym.embed_fail", module=module, file=file_rel, err=str(e))
        return 0
    written = 0
    for s, text, vec in zip(public_syms, texts, vecs, strict=True):
        try:
            _db.upsert_sym(
                db_path, kind="sym", text=text, file_path=file_rel,
                symbol_name=s.name, module=module,
                line_start=s.line_start, line_end=s.line_end,
                commit_sha=commit_sha, embedding=vec,
            )
            emit(log_path, component="code-index", level="info",
                 event="sym.upsert", module=module, file=file_rel,
                 symbol=s.name, sha=commit_sha)
            written += 1
        except Exception as e:
            emit(log_path, component="code-index", level="error",
                 event="sym.upsert_fail", module=module, file=file_rel,
                 symbol=s.name, err=str(e))
    return written
