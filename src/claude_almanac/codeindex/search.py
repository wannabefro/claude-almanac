"""Query the code-index DB and format results for retrieve injection."""
from __future__ import annotations

from claude_almanac.codeindex import db as _db
from claude_almanac.codeindex import fuse as _fuse
from claude_almanac.codeindex import keyword as _keyword
from claude_almanac.embedders import profiles as _embedder_profiles


def resolve_min_confidence(
    cfg_value: float | None,
    embedder_provider: str,
    embedder_model: str,
) -> float | None:
    """Resolve the effective ``min_confidence_distance`` for a caller.

    Precedence: explicit cfg override → embedder profile default → None
    (filter disabled). ``cfg_value`` ≤ 0 also disables the filter so
    users can opt out without editing the profile.
    """
    if cfg_value is not None:
        return cfg_value if cfg_value > 0 else None
    try:
        profile = _embedder_profiles.get(embedder_provider, embedder_model)
    except KeyError:
        return None
    return profile.min_confidence_distance


def _filter_low_confidence(
    vec_hits: list[dict[str, object]],
    kw_hits: list[dict[str, object]],
    min_confidence_distance: float | None,
) -> list[dict[str, object]]:
    """Drop vector-channel hits whose distance exceeds the confidence
    threshold AND which aren't independently confirmed by the keyword
    channel. A positive threshold enables the filter; ``None`` / 0 /
    negative leaves the channel untouched."""
    if min_confidence_distance is None or min_confidence_distance <= 0:
        return vec_hits
    kw_ids = {int(h["id"]) for h in kw_hits}  # type: ignore[call-overload]
    kept: list[dict[str, object]] = []
    for h in vec_hits:
        dist = h.get("distance")
        if (
            isinstance(dist, (int, float))
            and float(dist) > min_confidence_distance
            and int(h["id"]) not in kw_ids  # type: ignore[call-overload]
        ):
            continue
        kept.append(h)
    return kept


def _hybrid_sym(
    db_path: str, query_vec: list[float], query: str, k: int,
    module: str | None,
    min_confidence_distance: float | None,
) -> list[dict[str, object]]:
    """Vector + keyword channels fused via RRF. Fetches 2*k per channel so
    fusion has headroom to reorder. If a confidence threshold is set,
    vector-only hits beyond it are dropped before fusion — keyword-
    confirmed hits are always preserved."""
    fetch = max(k * 2, 10)
    vec_hits = _db.search(
        db_path, embedding=query_vec, k=fetch, kind="sym", module=module,
    )
    kw_hits = _keyword.search(db_path, query=query, k=fetch, kind="sym")
    vec_hits = _filter_low_confidence(vec_hits, kw_hits, min_confidence_distance)
    fused = _fuse.rrf([vec_hits, kw_hits], top_k=k)
    for r in fused:
        r.setdefault("kind", "sym")
    return fused


def search_and_format(db_path: str, *, query_vec: list[float],
                      sym_k: int, arch_k: int,
                      module: str | None = None,
                      kind: str | None = None,
                      query: str | None = None,
                      hybrid: bool = False,
                      min_confidence_distance: float | None = None) -> str:
    """Format code-index hits as a ``## Relevant code`` block.

    ``min_confidence_distance`` (v0.3.14): if set, drops vector-only sym
    hits whose distance exceeds the threshold so no-match queries return
    an empty string instead of the 3 nearest unrelated symbols. Arch
    hits are not filtered — module summaries are coarser and a
    too-strict cutoff would blank arch injection too aggressively.
    """
    results: list[dict[str, object]] = []
    use_hybrid = hybrid and bool(query)
    if kind in (None, "sym"):
        if use_hybrid:
            results += _hybrid_sym(
                db_path, query_vec, query or "", sym_k, module,
                min_confidence_distance,
            )
        else:
            vec_hits = _db.search(
                db_path, embedding=query_vec, k=sym_k,
                kind="sym", module=module,
            )
            results += _filter_low_confidence(
                vec_hits, [], min_confidence_distance,
            )
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
