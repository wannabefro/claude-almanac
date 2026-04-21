"""Hybrid (vector + keyword + RRF) retrieval wired into search_and_format."""
from __future__ import annotations

import pytest

from claude_almanac.contentindex import db as ci_db
from claude_almanac.contentindex import search as ci_search


@pytest.fixture
def indexed_db(tmp_path):
    """Same synthetic index as test_retrieval_quality_fixtures but re-built
    here to decouple — Task 1's red baseline stays a stable reference."""
    dbp = str(tmp_path / "hybrid.db")
    ci_db.init(dbp, dim=2)
    symbols = [
        ("Model", "internal/report/tuireport/model.go", "internal/report/tuireport",
         "// internal/report/tuireport/model.go  [type]  Model", [0.10, 0.90]),
        ("SegmentBuilder", "python/klaviyo/segmentation/builder.py", "python/klaviyo/segmentation",
         "// python/klaviyo/segmentation/builder.py  [class]  SegmentBuilder", [0.90, 0.10]),
        ("CHAT_SYSTEM_PROMPT", "python/klaviyo/chat/prompts.py", "python/klaviyo/chat",
         "// python/klaviyo/chat/prompts.py  [variable]  CHAT_SYSTEM_PROMPT", [0.70, 0.30]),
        ("TestBaseline", "tests/test_baseline.py", "tests",
         "// tests/test_baseline.py  [function]  TestBaseline", [0.50, 0.50]),
        ("TestRegression", "tests/test_regression.py", "tests",
         "// tests/test_regression.py  [function]  TestRegression", [0.52, 0.48]),
    ]
    for name, fp, mod, text, emb in symbols:
        ci_db.upsert(
            dbp, kind="sym", text=text, file_path=fp, symbol_name=name,
            module=mod, line_start=1, line_end=1, commit_sha="sha1",
            embedding=emb,
        )
    return dbp


def test_hybrid_surfaces_domain_symbol_for_terse_query(indexed_db):
    """The whole point of v0.3.11: terse 'tui' query (centroid-like vector)
    surfaces Model via the keyword channel's file_path match."""
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.50, 0.50], sym_k=3, arch_k=0,
        query="tui", hybrid=True,
    )
    assert "Model" in out


def test_hybrid_surfaces_segmentation(indexed_db):
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.55, 0.45], sym_k=3, arch_k=0,
        query="segmentation", hybrid=True,
    )
    assert "SegmentBuilder" in out


def test_hybrid_disabled_restores_vector_only_behaviour(indexed_db):
    """hybrid=False preserves v0.3.10 behaviour — regression safety."""
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.50, 0.50], sym_k=3, arch_k=0,
        query="tui", hybrid=False,
    )
    # Centroid-like vector returns noise symbols, keyword channel NOT consulted
    assert "TestBaseline" in out
    assert "Model" not in out


def test_hybrid_with_empty_query_falls_back_to_vector_only(indexed_db):
    """If no query string is passed (legacy callers), hybrid silently
    degrades to vector-only — no keyword channel to consult."""
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.50, 0.50], sym_k=3, arch_k=0,
        hybrid=True,  # no `query=` kwarg
    )
    # Falls through to vector-only behaviour
    assert "TestBaseline" in out


def test_hybrid_preserves_sym_arch_split(indexed_db):
    """Formatting output still has sym/arch sections. Arch happens to be
    empty in this fixture but the section header should be suppressed,
    not emitted with empty content."""
    out = ci_search.search_and_format(
        indexed_db, query_vec=[0.50, 0.50], sym_k=3, arch_k=0,
        query="tui", hybrid=True,
    )
    assert "### Symbols" in out
    assert "### Modules" not in out  # arch_k=0, no arch hits
