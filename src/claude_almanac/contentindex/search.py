"""Shared retrieval orchestrator for the content-index engine.

Runs a hybrid sym channel (vector + keyword fused via RRF), a vector-only
arch channel, a low-confidence distance filter on vector-only sym hits,
and a structural-symbol demotion pass to keep hijackers like ``LOGGER``
from crowding out named domain symbols. Formats the merged result as a
markdown block for retrieve-hook injection.

v0.4: per-kind scoring rules (structural-penalty sets, penalty
multipliers, vector demotion, per-kind confidence cutoff) are supplied
via :class:`~claude_almanac.contentindex.scoring.ScoringProfile`. Callers
pass ``scoring=CODE_PROFILE`` from :mod:`claude_almanac.codeindex.scoring`
for the v0.3.14 code-index behavior. Omitting ``scoring`` (or passing
``ScoringProfile()``) gives plain keyword-count scoring with no demotion
— the shape future ``kind='doc'`` callers will use.

The ``"## Relevant code"`` header emitted by ``search_and_format`` is
currently code-specific; Task 6 will make it kind-aware so ``doc`` hits
render under their own heading.
"""
from __future__ import annotations

from claude_almanac.contentindex import db as _db
from claude_almanac.contentindex import fuse as _fuse
from claude_almanac.contentindex import keyword as _keyword
from claude_almanac.contentindex.scoring import ScoringProfile
from claude_almanac.embedders import profiles as _embedder_profiles


def _demote_structural_unnamed(
    hits: list[dict[str, object]], query: str,
    *,
    structural_names: frozenset[str],
) -> list[dict[str, object]]:
    """Move vector hits whose ``symbol_name`` is in ``structural_names``
    and didn't match any query token to the end of the list, preserving
    relative order otherwise (v0.3.14).

    The keyword channel already penalizes these rows via the score
    multiplier in ``keyword.search``. The vector channel has no such
    signal — qwen3-embedding happily ranks ``LOGGER`` at d<0.75 for
    any rollup-adjacent query because the embedding model learned
    that ``LOGGER`` lives near rollup code textually. Demoting
    (instead of dropping) keeps the hit available if nothing else
    surfaces, but drops its RRF contribution to the back of the
    list so named domain symbols win top-3.
    """
    tokens = _keyword._tokenise(query)
    if not tokens:
        return hits
    kept: list[dict[str, object]] = []
    demoted: list[dict[str, object]] = []
    for h in hits:
        name = str(h.get("symbol_name") or "").lower()
        if name in structural_names and not any(t in name for t in tokens):
            demoted.append(h)
        else:
            kept.append(h)
    return kept + demoted


def resolve_min_confidence(
    cfg_value: float | None,
    embedder_provider: str,
    embedder_model: str,
    *,
    profile: ScoringProfile | None = None,
) -> float | None:
    """Resolve the effective ``min_confidence_distance`` for a caller.

    Precedence: ``profile.min_confidence_distance`` → explicit ``cfg_value``
    → embedder profile default → ``None`` (filter disabled). Any value
    ≤ 0 also disables the filter so users can opt out without editing
    the embedder profile.
    """
    if profile is not None and profile.min_confidence_distance is not None:
        v = profile.min_confidence_distance
        return v if v > 0 else None
    if cfg_value is not None:
        return cfg_value if cfg_value > 0 else None
    try:
        embedder_profile = _embedder_profiles.get(embedder_provider, embedder_model)
    except KeyError:
        return None
    return embedder_profile.min_confidence_distance


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
    scoring: ScoringProfile,
    min_confidence_distance: float | None,
) -> list[dict[str, object]]:
    """Vector + keyword channels fused via RRF. Fetches 2*k per channel so
    fusion has headroom to reorder. If a confidence threshold is set,
    vector-only hits beyond it are dropped before fusion — keyword-
    confirmed hits are always preserved. If the profile enables vector
    demotion, un-named structural symbols are moved to the back of the
    vector list before fusion."""
    fetch = max(k * 2, 10)
    vec_hits = _db.search(
        db_path, embedding=query_vec, k=fetch, kind="sym", module=module,
    )
    kw_hits = _keyword.search(
        db_path, query=query, k=fetch, kind="sym", scoring=scoring,
    )
    vec_hits = _filter_low_confidence(vec_hits, kw_hits, min_confidence_distance)
    if scoring.demote_structural_in_vector:
        vec_hits = _demote_structural_unnamed(
            vec_hits, query, structural_names=scoring.structural_names,
        )
    fused = _fuse.rrf([vec_hits, kw_hits], top_k=k)
    for r in fused:
        r.setdefault("kind", "sym")
    return fused


def _hybrid_doc(
    db_path: str, query_vec: list[float], query: str, k: int,
    module: str | None,
    scoring: ScoringProfile,
) -> list[dict[str, object]]:
    """Vector + keyword channels fused via RRF for kind='doc' rows.

    Mirrors ``_hybrid_sym`` but omits the low-confidence distance filter
    (doc chunks don't have the v0.3.14 hijacker problem — DOC_PROFILE is
    a no-op today). If the profile enables vector demotion, un-named
    structural entries are moved to the back before fusion."""
    fetch = max(k * 2, 10)
    vec_hits = _db.search(
        db_path, embedding=query_vec, k=fetch, kind="doc", module=module,
    )
    kw_hits = _keyword.search(
        db_path, query=query, k=fetch, kind="doc", scoring=scoring,
    )
    if scoring.demote_structural_in_vector:
        vec_hits = _demote_structural_unnamed(
            vec_hits, query, structural_names=scoring.structural_names,
        )
    fused = _fuse.rrf([vec_hits, kw_hits], top_k=k)
    for r in fused:
        r.setdefault("kind", "doc")
    return fused


def search_and_format(db_path: str, *, query_vec: list[float],
                      sym_k: int, arch_k: int,
                      doc_k: int = 0,
                      module: str | None = None,
                      kind: str | None = None,
                      query: str | None = None,
                      hybrid: bool = False,
                      min_confidence_distance: float | None = None,
                      scoring: dict[str, ScoringProfile] | ScoringProfile
                        | None = None) -> str:
    """Format content-index hits as a markdown block.

    The top-level ``"## Relevant code"`` heading now covers three
    sub-sections: ``### Symbols`` (sym), ``### Modules`` (arch), and
    ``### Docs`` (doc). ``core/retrieve.py`` handles any additional
    structure in the auto-inject flow.

    ``scoring`` (v0.4): either a per-kind ``{kind: ScoringProfile}`` dict
    or a single ``ScoringProfile`` (interpreted as the sym profile, for
    v0.3 legacy callers). Defaults to an empty dict so tests and
    ``doc``-only callers can omit it. Code-index callers pass
    :data:`claude_almanac.codeindex.scoring.CODE_PROFILE`; doc callers
    pass :data:`claude_almanac.documents.scoring.DOC_PROFILE`.

    ``min_confidence_distance`` (v0.3.14): if set, drops vector-only sym
    hits whose distance exceeds the threshold so no-match queries return
    an empty string instead of the 3 nearest unrelated symbols. Arch
    hits are not filtered — module summaries are coarser and a
    too-strict cutoff would blank arch injection too aggressively.
    Doc hits are likewise not filtered here (DOC_PROFILE is a no-op
    today; doc-specific tuning is deferred to v0.4.1).
    """
    # Normalize scoring → dict
    scoring_map: dict[str, ScoringProfile]
    if scoring is None:
        scoring_map = {}
    elif isinstance(scoring, ScoringProfile):
        # legacy single-profile form: assume sym (keeps Task 1–2 tests green)
        scoring_map = {"sym": scoring}
    else:
        scoring_map = scoring
    sym_scoring = scoring_map.get("sym", ScoringProfile())
    doc_scoring = scoring_map.get("doc", ScoringProfile())

    results: list[dict[str, object]] = []
    use_hybrid = hybrid and bool(query)
    if kind in (None, "sym") and sym_k > 0:
        if use_hybrid:
            results += _hybrid_sym(
                db_path, query_vec, query or "", sym_k, module,
                sym_scoring,
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
    if kind in (None, "arch") and arch_k > 0:
        # Arch stays vector-only. Arch rows have no symbol_name and the text
        # is a multi-line module summary, so the keyword channel's first-line
        # match wouldn't help.
        results += _db.search(db_path, embedding=query_vec, k=arch_k,
                              kind="arch", module=module)
    if kind in (None, "doc") and doc_k > 0:
        if use_hybrid:
            results += _hybrid_doc(
                db_path, query_vec, query or "", doc_k, module,
                doc_scoring,
            )
        else:
            results += _db.search(
                db_path, embedding=query_vec, k=doc_k,
                kind="doc", module=module,
            )
    if not results:
        return ""
    sym_rows = [r for r in results if r["kind"] == "sym"]
    arch_rows = [r for r in results if r["kind"] == "arch"]
    doc_rows = [r for r in results if r["kind"] == "doc"]
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
    if doc_rows:
        from claude_almanac.documents.display import format_doc_hit
        lines.append("### Docs")
        for r in doc_rows:
            lines.append(format_doc_hit(r))
    return "\n".join(lines)
