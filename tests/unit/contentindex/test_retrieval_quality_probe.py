"""13-query probe regression fixtures for v0.3.14 retrieval-quality fixes.

Each Pattern (A, D, E) surfaced by the 2026-04-21 dogfood probe is encoded
as a minimal deterministic fixture. The assertions describe the post-fix
contract; they are marked ``xfail(strict=True)`` before their fix lands and
the decorator is removed as each task completes. When xfail-strict is on,
the CI build fails if the assertion starts passing without the decorator
removal — catching both "fix missed" and "fix landed but test not updated"
in one gate.

Companion to ``test_retrieval_quality_fixtures.py``, which locks the
v0.3.11 hybrid-retrieval baseline on 2D synthetic embeddings. That suite
is about vector-vs-hybrid layering; this one is about the scoring and
index-inclusion contracts added in v0.3.14.
"""
from __future__ import annotations

import pytest

from claude_almanac.codeindex.config import DEFAULT_EXCLUDES, _excluded
from claude_almanac.codeindex.scoring import CODE_PROFILE
from claude_almanac.contentindex import db as ci_db
from claude_almanac.contentindex import keyword as ci_keyword
from claude_almanac.contentindex import search as ci_search

# ---------------------------------------------------------------------------
# Pattern A — module-symbol hijack
# ---------------------------------------------------------------------------
#
# When a query's tokens only match a file's path (not any symbol's name and
# not the symbol text's first 200 chars), every symbol in that file ties on
# the keyword score. Tiebreak is shorter file_path, which is identical for
# same-file rows, so whichever row SQLite returns first wins — usually a
# short module-level constant like LOGGER or a dunder like __init__.
#
# Post-fix: a structural-symbol penalty drops those file-path-only hijacker
# rows below the behavioral functions the user actually wants.


@pytest.fixture
def hooks_file_db(tmp_path):
    """Single file with a module-level LOGGER and a multi-line function.

    Query 'hooks widgets' matches only file_path for both symbols — the
    shape that lets LOGGER out-rank the function on v0.3.13.
    """
    dbp = str(tmp_path / "pattern_a.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/widgets/hooks.py",
        symbol_name="LOGGER",
        module="src/widgets",
        line_start=5, line_end=5,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    ci_db.upsert(
        dbp, kind="sym",
        text=(
            "def process_widget_submission(payload: dict) -> None:\n"
            "    \"\"\"Validate and persist an incoming widget submission.\"\"\"\n"
            "    ..."
        ),
        file_path="src/widgets/hooks.py",
        symbol_name="process_widget_submission",
        module="src/widgets",
        line_start=15, line_end=40,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    return dbp


def test_pattern_a_function_outranks_module_logger(hooks_file_db):
    """Query that hits only via file_path should rank the behavioral
    function above the module-level LOGGER constant."""
    hits = ci_keyword.search(
        hooks_file_db, query="hooks widgets", k=5, scoring=CODE_PROFILE,
    )
    names = [h["symbol_name"] for h in hits]
    assert "process_widget_submission" in names
    assert "LOGGER" in names
    assert names.index("process_widget_submission") < names.index("LOGGER")


def test_pattern_a_dunder_init_penalized_on_filepath_only_match(tmp_path):
    """Package ``__init__`` must not outrank a deeper-path domain function
    when the query hits only via file_path.

    The fixture makes the bug case explicit: __init__.py has a SHORTER
    file_path than the domain function's file, so on v0.3.13 the shorter-
    file-path tiebreak lets __init__ rank first. The structural penalty
    should invert that.
    """
    dbp = str(tmp_path / "pattern_a_init.db")
    ci_db.init(dbp, dim=2)
    # Short file_path — wins tiebreak on v0.3.13. Deliberately avoid the
    # token 'pipeline' anywhere in symbol_name or text so the match is
    # truly file_path-only (the shape the penalty targets).
    ci_db.upsert(
        dbp, kind="sym",
        text="from .core import runner_main\n",
        file_path="pipeline/__init__.py",
        symbol_name="__init__",
        module="pipeline",
        line_start=1, line_end=1,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    # Longer file_path — loses tiebreak on v0.3.13 despite being the
    # domain function the user actually wants.
    ci_db.upsert(
        dbp, kind="sym",
        text=(
            "def runner_main(config: Config) -> Result:\n"
            "    \"\"\"Execute the pipeline end-to-end.\"\"\"\n"
            "    ..."
        ),
        file_path="pipeline/execution/runner.py",
        symbol_name="runner_main",
        module="pipeline",
        line_start=10, line_end=30,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    hits = ci_keyword.search(dbp, query="pipeline", k=5, scoring=CODE_PROFILE)
    names = [h["symbol_name"] for h in hits]
    assert "runner_main" in names
    assert "__init__" in names
    assert names.index("runner_main") < names.index("__init__")


def test_pattern_a_user_querying_logger_by_name_still_works(hooks_file_db):
    """Counter-fixture: when the user literally queries ``LOGGER``, the
    symbol_name column matches directly and the structural penalty must
    NOT apply. Locks that the fix doesn't over-reach."""
    hits = ci_keyword.search(
        hooks_file_db, query="logger widgets", k=5, scoring=CODE_PROFILE,
    )
    names = [h["symbol_name"] for h in hits]
    assert "LOGGER" in names
    # LOGGER's symbol_name matched 'logger' token AND file_path matched
    # 'widgets' token — score=2 with no penalty. Function matched only
    # via file_path on 'widgets' token — score=1. LOGGER should win.
    assert names[0] == "LOGGER"


# ---------------------------------------------------------------------------
# Pattern D — .d.ts / .output/ duplication
# ---------------------------------------------------------------------------
#
# TypeScript packages ship generated .d.ts files alongside or in .output/
# dist/ build/ trees. They re-declare the same symbol signatures as the
# source .ts, so identical queries return both. Post-fix: the glob-exclude
# list skips these at index time.


def test_pattern_d_default_excludes_cover_output_and_dts():
    """DEFAULT_EXCLUDES must skip .output/ trees and any *.d.ts file
    regardless of depth. dist/ and build/ are already excluded on
    v0.3.13; they're here as positive controls."""
    cases = [
        "packages/foo/.output/types/foo.d.ts",
        "packages/foo/.output/index.js",
        "packages/foo/dist/bundle.js",
        "packages/foo/build/main.js",
        "packages/foo/src/foo.d.ts",
        ".output/shallow.ts",
    ]
    for rel in cases:
        assert _excluded(rel, DEFAULT_EXCLUDES), (
            f"expected {rel!r} to be excluded by DEFAULT_EXCLUDES"
        )


def test_pattern_d_source_ts_is_not_excluded():
    """Locks that the new excludes don't nuke real source .ts files."""
    for rel in ["packages/foo/src/foo.ts", "src/components/Button.tsx"]:
        assert not _excluded(rel, DEFAULT_EXCLUDES), (
            f"{rel!r} should NOT be excluded"
        )


# ---------------------------------------------------------------------------
# Pattern E — no-confidence false positive
# ---------------------------------------------------------------------------
#
# For queries with no real match in the repo (irrelevant concept, degenerate
# single token), vector-only search returns the 3 nearest symbols regardless
# of how distant they all are. Agents consume these as confident answers.
# Post-fix: a distance threshold filters them out so empty results surface
# through the existing "no matches" path.


@pytest.fixture
def cooking_db(tmp_path):
    """A tiny repo about cooking. Queries about unrelated concepts
    (blockchain) embed far away from every symbol, producing large L2
    distances across the board."""
    dbp = str(tmp_path / "pattern_e.db")
    ci_db.init(dbp, dim=2)
    rows = [
        ("knead_dough",  "src/cooking/dough.py",  [0.90, 0.10]),
        ("simmer_stock", "src/cooking/stock.py",  [0.80, 0.20]),
        ("fold_butter",  "src/cooking/pastry.py", [0.85, 0.15]),
    ]
    for name, fp, emb in rows:
        ci_db.upsert(
            dbp, kind="sym",
            text=f"def {name}(): ...",
            file_path=fp,
            symbol_name=name,
            module="src/cooking",
            line_start=1, line_end=1,
            commit_sha="sha1",
            embedding=emb,
        )
    return dbp


def test_pattern_e_off_topic_query_returns_no_matches(cooking_db):
    """Query for an unrelated concept (blockchain) against a cooking
    repo. All hits have large L2 distance; the filter drops them and
    search_and_format returns empty (the existing no-results signal)."""
    # Query vector lives on the opposite side of the unit square from
    # every indexed symbol. L2 distances all land >= ~0.99.
    out = ci_search.search_and_format(
        cooking_db, query_vec=[0.05, 0.95],
        sym_k=3, arch_k=0,
        query="blockchain wallet", hybrid=True,
        min_confidence_distance=0.95,
    )
    assert out == "", (
        "low-confidence hits must be dropped, not surfaced under a "
        "'## Relevant code' heading"
    )


def test_pattern_e_on_topic_query_still_returns_results(cooking_db):
    """Counter-fixture: when the query embeds near an indexed symbol,
    distance is low and the result surfaces as before."""
    out = ci_search.search_and_format(
        cooking_db, query_vec=[0.89, 0.11],
        sym_k=3, arch_k=0,
        query="knead dough bread", hybrid=True,
        min_confidence_distance=0.95,
    )
    assert "knead_dough" in out


def test_pattern_e_threshold_none_disables_filter(cooking_db):
    """Default behavior when ``min_confidence_distance`` is None: filter
    is off, even nonsense queries surface their nearest-k. Locks that
    existing callers without the new knob aren't silently changed."""
    out = ci_search.search_and_format(
        cooking_db, query_vec=[0.05, 0.95],
        sym_k=3, arch_k=0,
        query="blockchain wallet", hybrid=True,
    )
    assert "knead_dough" in out or "simmer_stock" in out or "fold_butter" in out


def test_pattern_e_keyword_confirmed_hit_bypasses_filter(cooking_db):
    """A hit present in the keyword channel is kept even when its
    vector distance exceeds the confidence threshold — keyword
    confirmation is an independent signal of relevance."""
    # Query embeds far from every symbol (same vector as off-topic test),
    # but 'knead' matches knead_dough's symbol_name on the keyword
    # channel → kept despite large vector distance.
    out = ci_search.search_and_format(
        cooking_db, query_vec=[0.05, 0.95],
        sym_k=3, arch_k=0,
        query="knead", hybrid=True,
        min_confidence_distance=0.95,
    )
    assert "knead_dough" in out


# ---------------------------------------------------------------------------
# Pattern A (extended) — vector-channel structural demotion (v0.3.14)
# ---------------------------------------------------------------------------
#
# The keyword-channel penalty alone doesn't stop ``LOGGER`` surfacing in
# top-3 when the vector embedding ranks it high on its own. Observed on
# 2026-04-21 dogfood: query "session rollup idle timeout trigger" hit
# LOGGER (in hooks/retrieve.py) at d=0.746 — well inside the confidence
# filter. The vector channel has no structural-symbol signal, so we
# demote ``LOGGER`` / ``__init__`` / ``__main__`` / ``dispatch`` hits
# whose names didn't match any query token to the end of the vector
# list before fusion.


def test_pattern_a_vector_logger_demoted_when_unnamed(tmp_path):
    """LOGGER with a small vector distance must NOT out-rank a named
    domain symbol that matches the query on name.

    Fixture: two symbols. LOGGER has an embedding very close to the
    query vector (distance ~0.1). ``process_event`` has an embedding
    further away but its name matches the query. Before demotion,
    LOGGER wins vector rank 1 and RRF-fuses to top; after demotion,
    LOGGER goes to the bottom of vec_hits and process_event wins.
    """
    dbp = str(tmp_path / "demote.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/events/bus.py",
        symbol_name="LOGGER",
        module="src/events",
        line_start=3, line_end=3,
        commit_sha="sha1",
        embedding=[0.40, 0.60],  # close to query vector
    )
    ci_db.upsert(
        dbp, kind="sym",
        text=(
            "def process_event(evt: Event) -> None:\n"
            "    \"\"\"Dispatch event to registered handlers.\"\"\"\n"
            "    ..."
        ),
        file_path="src/events/bus.py",
        symbol_name="process_event",
        module="src/events",
        line_start=10, line_end=30,
        commit_sha="sha1",
        embedding=[0.10, 0.90],  # farther from query
    )
    # Query vector close to LOGGER but query text names "process_event"
    # via the 'process' / 'event' tokens.
    out = ci_search.search_and_format(
        dbp, query_vec=[0.42, 0.58],
        sym_k=3, arch_k=0,
        query="process event dispatch", hybrid=True,
        scoring=CODE_PROFILE,
    )
    # Both should be present, but process_event must win ranking.
    assert "process_event" in out
    pos_named = out.index("process_event")
    if "LOGGER" in out:
        assert pos_named < out.index("LOGGER")


def test_pattern_a_vector_logger_preserved_when_named(tmp_path):
    """Counter: if the query explicitly names LOGGER, it must NOT be
    demoted. This is the minimum-viable single-symbol case — only
    LOGGER in the DB, user asks for LOGGER, the hit surfaces."""
    dbp = str(tmp_path / "demote_named.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/core/base.py",
        symbol_name="LOGGER",
        module="src/core",
        line_start=3, line_end=3,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    out = ci_search.search_and_format(
        dbp, query_vec=[0.5, 0.5],
        sym_k=3, arch_k=0,
        query="logger base setup", hybrid=True,
    )
    assert "LOGGER" in out


def test_pattern_a_demotion_no_query_tokens_skipped(tmp_path):
    """If the query has no tokens passing the 3-char floor (e.g.,
    punctuation or empty), the demotion is a no-op — we can't tell
    intent, so we preserve vector rank. Locks a defensive branch."""
    dbp = str(tmp_path / "demote_empty.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/core/base.py",
        symbol_name="LOGGER",
        module="src/core",
        line_start=3, line_end=3,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    out = ci_search.search_and_format(
        dbp, query_vec=[0.5, 0.5],
        sym_k=3, arch_k=0,
        query="", hybrid=True,  # empty → no tokens → no-op demotion
    )
    # Empty query → hybrid path disabled (needs bool(query)), so this
    # tests the non-hybrid path which doesn't demote either. Purely
    # asserts no crash + LOGGER surfaces via vector-only path.
    assert "LOGGER" in out
