"""Query the code-index DB and format results for retrieve injection."""
from __future__ import annotations

from claude_almanac.codeindex import db as _db
from claude_almanac.codeindex import fuse as _fuse
from claude_almanac.codeindex import keyword as _keyword


def _hybrid_sym(
    db_path: str, query_vec: list[float], query: str, k: int,
    module: str | None,
) -> list[dict[str, object]]:
    """Vector + keyword channels fused via RRF. Fetches 2*k per channel so
    fusion has headroom to reorder."""
    fetch = max(k * 2, 10)
    vec_hits = _db.search(
        db_path, embedding=query_vec, k=fetch, kind="sym", module=module,
    )
    kw_hits = _keyword.search(db_path, query=query, k=fetch, kind="sym")
    fused = _fuse.rrf([vec_hits, kw_hits], top_k=k)
    for r in fused:
        r.setdefault("kind", "sym")
    return fused


def search_and_format(db_path: str, *, query_vec: list[float],
                      sym_k: int, arch_k: int,
                      module: str | None = None,
                      kind: str | None = None,
                      query: str | None = None,
                      hybrid: bool = False) -> str:
    results: list[dict[str, object]] = []
    use_hybrid = hybrid and bool(query)
    if kind in (None, "sym"):
        if use_hybrid:
            results += _hybrid_sym(db_path, query_vec, query or "", sym_k, module)
        else:
            results += _db.search(db_path, embedding=query_vec, k=sym_k,
                                  kind="sym", module=module)
    if kind in (None, "arch"):
        # Arch stays vector-only. Arch rows have no symbol_name and the text
        # is a multi-line module summary, so the keyword channel's first-line
        # match wouldn't help.
        results += _db.search(db_path, embedding=query_vec, k=arch_k,
                              kind="arch", module=module)
    if not results:
        return ""
    sym_rows = [r for r in results if r["kind"] == "sym"]
    arch_rows = [r for r in results if r["kind"] == "arch"]
    lines = ["## Relevant code"]
    if sym_rows:
        lines.append("### Symbols")
        for r in sym_rows:
            loc = f'{r["file_path"]}:{r["line_start"]}-{r["line_end"]}'
            text = r.get("text")
            first = text.splitlines()[0][:100] if isinstance(text, str) else ""
            lines.append(f'- [sym] {loc}  {r["symbol_name"]} — {first}')
    if arch_rows:
        lines.append("### Modules")
        for r in arch_rows:
            text = r.get("text")
            short = (text if isinstance(text, str) else "").replace("\n", " ")[:160]
            lines.append(f'- [arch] {r["module"]} — {short}')
    return "\n".join(lines)
