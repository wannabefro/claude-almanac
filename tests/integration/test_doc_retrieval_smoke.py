"""Integration smoke (live Ollama + real markdown): confirm doc
retrieval returns a plausible hit on a known query. Runs on the
release-branch CI gate only, per tests/integration conventions.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_doc_retrieval_smoke_round_trip(tmp_path):
    from claude_almanac.contentindex import db as cdb
    from claude_almanac.contentindex import search as csearch
    from claude_almanac.documents import ingest
    from claude_almanac.documents.scoring import DOC_PROFILE
    from claude_almanac.embedders.factory import make_embedder

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/arch.md").write_text(
        "# Architecture\n\n"
        "## UserPromptSubmit hook\n\n"
        "The UserPromptSubmit hook injects memory and code into the prompt.\n"
    )

    emb = make_embedder("ollama", "qwen3-embedding:0.6b")
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=emb.dim)
    n = ingest.index_repo(
        repo_root=str(tmp_path), db_path=dbp, embedder=emb,
        patterns=["docs/**"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200,
        commit_sha="s",
    )
    assert n >= 1

    [vec] = emb.embed(["how does the user prompt submit hook inject context"])
    out = csearch.search_and_format(
        dbp, query_vec=vec, sym_k=0, arch_k=0, doc_k=3, kind="doc",
        query="user prompt submit hook inject", hybrid=True,
        scoring={"doc": DOC_PROFILE},
    )
    assert "UserPromptSubmit" in out, (
        f"expected 'UserPromptSubmit' in doc retrieval output; got:\n{out}"
    )
