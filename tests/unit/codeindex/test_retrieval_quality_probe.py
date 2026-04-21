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

from claude_almanac.codeindex import db as ci_db
from claude_almanac.codeindex import keyword as ci_keyword
from claude_almanac.codeindex import search as ci_search
from claude_almanac.codeindex.config import DEFAULT_EXCLUDES, _excluded

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
    ci_db.upsert_sym(
        dbp, kind="sym",
        text="LOGGER = logging.getLogger(__name__)",
        file_path="src/widgets/hooks.py",
        symbol_name="LOGGER",
        module="src/widgets",
        line_start=5, line_end=5,
        commit_sha="sha1",
        embedding=[0.5, 0.5],
    )
    ci_db.upsert_sym(
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
    hits = ci_keyword.search(hooks_file_db, query="hooks widgets", k=5)
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
    ci_db.upsert_sym(
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
    ci_db.upsert_sym(
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
    hits = ci_keyword.search(dbp, query="pipeline", k=5)
    names = [h["symbol_name"] for h in hits]
    assert "runner_main" in names
    assert "__init__" in names
    assert names.index("runner_main") < names.index("__init__")


def test_pattern_a_user_querying_logger_by_name_still_works(hooks_file_db):
    """Counter-fixture: when the user literally queries ``LOGGER``, the
    symbol_name column matches directly and the structural penalty must
    NOT apply. Locks that the fix doesn't over-reach."""
    hits = ci_keyword.search(hooks_file_db, query="logger widgets", k=5)
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
        ci_db.upsert_sym(
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


@pytest.mark.xfail(
    strict=True,
    reason="v0.3.14 Task 4: low-confidence distance filter",
)
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
    )
    assert "knead_dough" in out
