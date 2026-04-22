"""Cross-subsystem integration: code + doc rows, unified retrieval."""
from __future__ import annotations

import pytest

from claude_almanac.codeindex.scoring import CODE_PROFILE
from claude_almanac.contentindex import db as cdb
from claude_almanac.contentindex import search as csearch
from claude_almanac.documents.scoring import DOC_PROFILE


@pytest.fixture
def mixed_db(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=2)
    # Code row
    cdb.upsert(dbp, kind="sym",
               text="def run(config): ...", file_path="src/cli.py",
               symbol_name="run", module="src",
               line_start=1, line_end=10, commit_sha="s",
               embedding=[0.1, 0.9])
    # Doc row close to the query vector
    cdb.upsert(dbp, kind="doc",
               text="// docs/cli.md [doc] Running\n# Running\n\nUse run().",
               file_path="docs/cli.md", symbol_name="Running",
               module="docs", line_start=1, line_end=5,
               commit_sha="s", embedding=[0.11, 0.89])
    return dbp


def test_search_and_format_surfaces_three_sections(mixed_db):
    out = csearch.search_and_format(
        mixed_db, query_vec=[0.1, 0.9],
        sym_k=3, arch_k=0, doc_k=3,
        kind=None,  # all kinds
        query="run cli",
        hybrid=True,
        scoring={"sym": CODE_PROFILE, "doc": DOC_PROFILE},
    )
    assert "## Relevant code" in out
    assert "### Symbols" in out
    assert "### Docs" in out
    assert "run" in out          # sym row
    assert "Running" in out      # doc row
    assert "docs/cli.md" in out


def test_search_and_format_kind_filter_isolates_docs(mixed_db):
    out = csearch.search_and_format(
        mixed_db, query_vec=[0.1, 0.9],
        sym_k=0, arch_k=0, doc_k=3,
        kind="doc", query="run cli", hybrid=True,
        scoring={"doc": DOC_PROFILE},
    )
    assert "Running" in out
    # sym row 'run' lives at src/cli.py; kind filter should drop it entirely.
    assert "src/cli.py" not in out
