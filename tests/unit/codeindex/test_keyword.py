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


# ---------------------------------------------------------------------------
# Structural-symbol penalty (v0.3.14)
# ---------------------------------------------------------------------------


@pytest.fixture
def structural_penalty_db(tmp_path):
    """One file with a LOGGER, a single-line module-level constant, and
    a multi-line behavioral function. All three match the same file_path
    on the query 'routes api', so the penalty is what separates them."""
    dbp = str(tmp_path / "penalty.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert_sym(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/routes/api_v1.py",
        symbol_name="LOGGER",
        module="src/routes",
        line_start=3, line_end=3,
        commit_sha="sha1",
        embedding=[0.1, 0.1],
    )
    ci_db.upsert_sym(
        dbp, kind="sym",
        text='MAX_BATCH = 250',
        file_path="src/routes/api_v1.py",
        symbol_name="MAX_BATCH",
        module="src/routes",
        line_start=5, line_end=5,
        commit_sha="sha1",
        embedding=[0.2, 0.2],
    )
    ci_db.upsert_sym(
        dbp, kind="sym",
        text=(
            "def handle_submission(request: Request) -> Response:\n"
            "    \"\"\"Validate and dispatch the incoming submission.\"\"\"\n"
            "    ..."
        ),
        file_path="src/routes/api_v1.py",
        symbol_name="handle_submission",
        module="src/routes",
        line_start=10, line_end=50,
        commit_sha="sha1",
        embedding=[0.3, 0.3],
    )
    return dbp


def test_structural_name_demoted_on_filepath_only_match(structural_penalty_db):
    """When every row in a file ties on file_path-only matches, the
    structural-name penalty (0.4×) drops LOGGER below the domain function."""
    hits = ci_keyword.search(structural_penalty_db, query="routes api", k=5)
    names = [h["symbol_name"] for h in hits]
    assert names.index("handle_submission") < names.index("LOGGER")


def test_single_line_constant_demoted_on_filepath_only_match(structural_penalty_db):
    """Non-structural but single-line variables (MAX_BATCH) take the
    weaker 0.6× penalty — still below the multi-line function."""
    hits = ci_keyword.search(structural_penalty_db, query="routes api", k=5)
    names = [h["symbol_name"] for h in hits]
    assert names.index("handle_submission") < names.index("MAX_BATCH")


def test_symbol_name_match_bypasses_penalty(structural_penalty_db):
    """Querying ``LOGGER`` directly matches symbol_name, so the row is
    NOT file-path-only and no penalty applies — user intent respected."""
    hits = ci_keyword.search(structural_penalty_db, query="LOGGER routes", k=5)
    assert hits[0]["symbol_name"] == "LOGGER"


def test_text_body_match_bypasses_penalty(tmp_path):
    """If a query token matches the first-line text of a structural
    symbol (e.g., querying ``handler`` where LOGGER = logging.getLogger
    mentions 'getLogger'), the penalty must NOT apply.

    This is a narrower control — in practice LOGGER's body rarely
    encodes semantic query tokens, but we want the rule to be
    column-accurate, not name-accurate."""
    dbp = str(tmp_path / "text_match.db")
    ci_db.init(dbp, dim=2)
    # LOGGER whose text contains 'handler' — query matches text, not file_path.
    ci_db.upsert_sym(
        dbp, kind="sym",
        text="LOGGER = build_handler_logger()",
        file_path="src/core/base.py",
        symbol_name="LOGGER",
        module="src/core",
        line_start=1, line_end=1,
        commit_sha="sha1",
        embedding=[0.1, 0.1],
    )
    hits = ci_keyword.search(dbp, query="handler", k=5)
    # Score should be 1 (any_hits), name_text_hits = 1, no penalty.
    assert hits
    assert hits[0]["symbol_name"] == "LOGGER"
