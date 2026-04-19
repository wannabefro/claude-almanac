"""Query the code-index DB and format results for retrieve injection."""
from __future__ import annotations

from claude_almanac.codeindex import db as _db


def search_and_format(db_path: str, *, query_vec: list[float],
                      sym_k: int, arch_k: int,
                      module: str | None = None,
                      kind: str | None = None) -> str:
    results: list[dict[str, object]] = []
    if kind in (None, "sym"):
        results += _db.search(db_path, embedding=query_vec, k=sym_k,
                              kind="sym", module=module)
    if kind in (None, "arch"):
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
