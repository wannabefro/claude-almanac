"""Keyword retrieval channel (v0.3.11) — SQLite LIKE fallback used alongside
the vector channel for hybrid retrieval."""
from __future__ import annotations

import pytest

from claude_almanac.codeindex import db as ci_db
from claude_almanac.codeindex import keyword as ci_keyword


@pytest.fixture
def indexed_db(tmp_path):
    """Synthetic DB with domain symbols + noise, mirroring test_retrieval_quality_fixtures."""
    dbp = str(tmp_path / "kw.db")
    ci_db.init(dbp, dim=2)
    symbols = [
        # domain symbols
        ("Model", "internal/report/tuireport/model.go", "internal/report/tuireport",
         "// internal/report/tuireport/model.go  [type]  Model"),
        ("SegmentBuilder", "python/klaviyo/segmentation/builder.py", "python/klaviyo/segmentation",
         "// python/klaviyo/segmentation/builder.py  [class]  SegmentBuilder"),
        ("CHAT_SYSTEM_PROMPT", "python/klaviyo/chat/prompts.py", "python/klaviyo/chat",
         "// python/klaviyo/chat/prompts.py  [variable]  CHAT_SYSTEM_PROMPT"),
        # noise
        ("TestBaseline", "tests/test_baseline.py", "tests",
         "// tests/test_baseline.py  [function]  TestBaseline"),
    ]
    for i, (name, fp, mod, text) in enumerate(symbols):
        ci_db.upsert_sym(
            dbp, kind="sym", text=text, file_path=fp, symbol_name=name,
            module=mod, line_start=1, line_end=1, commit_sha="sha1",
            embedding=[float(i), float(i)],
        )
    return dbp


def test_finds_tui_model_via_file_path_substring(indexed_db):
    """The keyword 'tui' matches Model because its file_path contains 'tui'."""
    hits = ci_keyword.search(indexed_db, query="tui", k=5)
    names = [h["symbol_name"] for h in hits]
    assert "Model" in names


def test_finds_segmentation_via_file_path_substring(indexed_db):
    hits = ci_keyword.search(indexed_db, query="segmentation", k=5)
    names = [h["symbol_name"] for h in hits]
    assert "SegmentBuilder" in names


def test_finds_symbol_name_match(indexed_db):
    hits = ci_keyword.search(indexed_db, query="CHAT_SYSTEM_PROMPT", k=5)
    names = [h["symbol_name"] for h in hits]
    assert "CHAT_SYSTEM_PROMPT" in names


def test_empty_query_returns_empty(indexed_db):
    assert ci_keyword.search(indexed_db, query="", k=5) == []


def test_too_short_tokens_return_empty(indexed_db):
    """Tokens below the 3-char floor are dropped to prevent centroid-scan."""
    assert ci_keyword.search(indexed_db, query="ab", k=5) == []
    assert ci_keyword.search(indexed_db, query="a b c", k=5) == []


def test_multi_token_query_scores_more_matches_higher(indexed_db):
    """Two tokens both matching a symbol should out-rank a symbol hit by only
    one token."""
    # 'tui' matches Model's file_path; 'Model' matches Model's symbol_name.
    # Other symbols match neither.
    hits = ci_keyword.search(indexed_db, query="tui Model", k=5)
    assert hits
    assert hits[0]["symbol_name"] == "Model"


def test_wildcard_characters_escaped(indexed_db):
    """Query containing '%' or '_' must not wildcard-scan every row."""
    # '%' alone shouldn't match anything after escaping (and is below 3-char floor anyway)
    assert ci_keyword.search(indexed_db, query="%%%", k=5) == []


def test_returns_entry_row_shape(indexed_db):
    """Keyword hits must carry the same keys as vector hits so fuse.py can
    merge them."""
    hits = ci_keyword.search(indexed_db, query="tui", k=5)
    assert hits
    row = hits[0]
    required = {
        "id", "kind", "text", "file_path", "symbol_name", "module",
        "line_start", "line_end", "commit_sha",
    }
    assert required.issubset(row.keys())


def test_respects_k_limit(indexed_db):
    # All four symbols have "test" nowhere; "klaviyo" matches two.
    hits = ci_keyword.search(indexed_db, query="klaviyo chat", k=1)
    assert len(hits) == 1
