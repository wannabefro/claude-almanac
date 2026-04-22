"""Locked doc probe fixtures — 3 synthetic queries with known rankings.

These are smaller-scale versions of the live D1-D10 probes (which run
only post-merge against the author's real docs). Each fixture here
pins a specific retrieval shape the engine must preserve.
"""
from __future__ import annotations

import pytest

from claude_almanac.contentindex import db as cdb
from claude_almanac.contentindex import search as csearch
from claude_almanac.documents.scoring import DOC_PROFILE


@pytest.fixture
def synthetic_docs_db(tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=2)
    rows = [
        # Architecture doc, high match on "hook" + "inject"
        ("UserPromptSubmit",
         "docs/architecture.md",
         "// docs/architecture.md [doc] UserPromptSubmit hook\n"
         "The UserPromptSubmit hook injects memory and code into the prompt.\n",
         [0.10, 0.90]),
        # Trust boundary doc
        ("Trust boundary",
         "docs/codeindex.md",
         "// docs/codeindex.md [doc] Trust boundary\n"
         "Arch pass sends source to Anthropic; dual send_code_to_llm gate.\n",
         [0.20, 0.80]),
        # Decay doc
        ("Decay",
         "docs/decay.md",
         "// docs/decay.md [doc] Decay\n"
         "Score formula uses half-life and exponent.\n",
         [0.30, 0.70]),
        # Unrelated cooking doc (noise)
        ("Sauces",
         "docs/cooking.md",
         "// docs/cooking.md [doc] Sauces\n"
         "Emulsion and reduction techniques.\n",
         [0.90, 0.10]),
    ]
    for name, fp, text, emb in rows:
        cdb.upsert(dbp, kind="doc", text=text, file_path=fp,
                   symbol_name=name, module="docs",
                   line_start=1, line_end=3, commit_sha="s",
                   embedding=emb)
    return dbp


def test_query_about_hook_finds_userpromptsubmit(synthetic_docs_db):
    out = csearch.search_and_format(
        synthetic_docs_db, query_vec=[0.11, 0.89],
        sym_k=0, arch_k=0, doc_k=3, kind="doc",
        query="hook inject prompt", hybrid=True,
        scoring={"doc": DOC_PROFILE},
    )
    assert "UserPromptSubmit" in out


def test_query_about_trust_boundary_finds_arch_doc(synthetic_docs_db):
    out = csearch.search_and_format(
        synthetic_docs_db, query_vec=[0.21, 0.79],
        sym_k=0, arch_k=0, doc_k=3, kind="doc",
        query="trust boundary arch", hybrid=True,
        scoring={"doc": DOC_PROFILE},
    )
    assert "Trust boundary" in out


def test_unrelated_query_doesnt_pull_cooking(synthetic_docs_db):
    out = csearch.search_and_format(
        synthetic_docs_db, query_vec=[0.10, 0.90],
        sym_k=0, arch_k=0, doc_k=3, kind="doc",
        query="hook memory inject", hybrid=True,
        scoring={"doc": DOC_PROFILE},
    )
    # Cooking doc's vector is far; it shouldn't be in top-3 when 3
    # better matches exist.
    assert "Sauces" not in out
