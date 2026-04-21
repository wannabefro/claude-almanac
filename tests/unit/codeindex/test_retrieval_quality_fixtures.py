"""Retrieval-quality baseline for the hybrid-retrieval work (v0.3.11).

Synthesises a small code-index DB with known domain symbols (tui/, segmentation/,
prompts/) plus generic test-noise symbols (TestBaseline, TestRegression). Uses
hand-picked 2D embeddings that reproduce the real-world failure seen on
2026-04-21: under vector-only ranking, a terse query like "tui" maps near the
centroid and lets generic test symbols out-rank the domain-specific Model in
tuireport/model.go.

Until hybrid retrieval lands (Task 4), `test_terse_query_misses_domain_symbol_in_vector_only_mode`
documents the failure as a locked baseline. When hybrid wiring is added, the
test flips sense: keyword fallback finds Model via the file_path substring and
RRF fuses it into the top-3.
"""
from __future__ import annotations

import pytest

from claude_almanac.codeindex import db as ci_db
from claude_almanac.codeindex import search as ci_search


# --- synthetic index helpers --------------------------------------------------

# 2D embeddings chosen so that:
#   query "tui"          = [0.50, 0.50] (centroid; mimics terse-query ambiguity)
#   query "tui model"    = [0.15, 0.85] (richer; close to Model)
#   Model                = [0.10, 0.90] (far from "tui" centroid, close to
#                                        "tui model")
#   SegmentBuilder       = [0.90, 0.10]
#   CHAT_SYSTEM_PROMPT   = [0.70, 0.30]
#   TestBaseline         = [0.50, 0.50] (sits exactly on the centroid — this is
#                                        the noise that out-ranks Model on
#                                        terse queries)
#   TestRegression       = [0.52, 0.48]
#
# With L2 distance and these coordinates:
#   d(tui, TestBaseline)    = 0.00
#   d(tui, TestRegression)  ≈ 0.028
#   d(tui, CHAT_SYSTEM_PROMPT) ≈ 0.283
#   d(tui, Model)           ≈ 0.566   ← last of five
#   d(tui, SegmentBuilder)  ≈ 0.566
#
# So vector-only top-3 for "tui" = [TestBaseline, TestRegression, CHAT_SYSTEM_PROMPT].
# The domain-correct symbol (Model) is nowhere in the top-3.


FIXTURE_SYMBOLS: list[dict[str, object]] = [
    {
        "symbol_name": "Model",
        "file_path": "internal/report/tuireport/model.go",
        "module": "internal/report/tuireport",
        "text": "// internal/report/tuireport/model.go  [type]  Model",
        "embedding": [0.10, 0.90],
    },
    {
        "symbol_name": "SegmentBuilder",
        "file_path": "python/klaviyo/segmentation/segments_analyst/services/builder.py",
        "module": "python/klaviyo/segmentation",
        "text": "// python/klaviyo/segmentation/...builder.py  [class]  SegmentBuilder",
        "embedding": [0.90, 0.10],
    },
    {
        "symbol_name": "CHAT_SYSTEM_PROMPT",
        "file_path": "python/klaviyo/chat/prompts/chat_prompts.py",
        "module": "python/klaviyo/chat",
        "text": "// python/klaviyo/chat/prompts/chat_prompts.py  [variable]  CHAT_SYSTEM_PROMPT",
        "embedding": [0.70, 0.30],
    },
    {
        "symbol_name": "TestBaseline",
        "file_path": "tests/test_baseline.py",
        "module": "tests",
        "text": "// tests/test_baseline.py  [function]  TestBaseline",
        "embedding": [0.50, 0.50],
    },
    {
        "symbol_name": "TestRegression",
        "file_path": "tests/test_regression.py",
        "module": "tests",
        "text": "// tests/test_regression.py  [function]  TestRegression",
        "embedding": [0.52, 0.48],
    },
]


@pytest.fixture
def indexed_db(tmp_path):
    dbp = str(tmp_path / "fixture.db")
    ci_db.init(dbp, dim=2)
    for sym in FIXTURE_SYMBOLS:
        ci_db.upsert_sym(
            dbp,
            kind="sym",
            text=sym["text"],
            file_path=sym["file_path"],
            symbol_name=sym["symbol_name"],
            module=sym["module"],
            line_start=1,
            line_end=1,
            commit_sha="sha1",
            embedding=sym["embedding"],
        )
    return dbp


# --- baseline tests -----------------------------------------------------------

def test_terse_query_misses_domain_symbol_in_vector_only_mode(indexed_db):
    """Locked baseline: under vector-only search, query 'tui' ranks TestBaseline
    and TestRegression above Model.

    This test PASSES on v0.3.10 (the failure is the baseline). It is expected
    to FAIL once hybrid retrieval lands in Task 4 — at which point the test
    assertions should flip to the hybrid expectations (see sibling test below)
    and this test should be removed or renamed.
    """
    # "tui" embeds to the centroid [0.50, 0.50]
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.50, 0.50], sym_k=3, arch_k=0,
    )
    assert "## Relevant code" in out
    assert "TestBaseline" in out
    assert "TestRegression" in out
    # The domain-correct symbol does NOT surface — this is the bug.
    assert "Model" not in out


def test_richer_query_finds_domain_symbol_in_vector_only_mode(indexed_db):
    """Counterfactual: the index is correct — Model surfaces when the query
    embeds close to it. Documents that the problem is query-side, not
    index-side."""
    # "tui terminal report Model" embeds closer to [0.15, 0.85]
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.15, 0.85], sym_k=3, arch_k=0,
    )
    assert "Model" in out


def test_terse_segmentation_query_misses_domain_symbol_in_vector_only_mode(
    indexed_db,
):
    """Mirrors the k-repo 'segmentation' failure: the centroid-like query
    ranks generic symbols above SegmentBuilder."""
    # A different terse-query centroid
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.55, 0.45], sym_k=3, arch_k=0,
    )
    assert "SegmentBuilder" not in out
