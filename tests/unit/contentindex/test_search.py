from claude_almanac.contentindex import db as ci_db
from claude_almanac.contentindex import search as ci_search


def test_format_hits_renders_sym_and_arch_sections(tmp_path):
    dbp = str(tmp_path / "ci.db")
    ci_db.init(dbp, dim=2)
    ci_db.upsert_sym(dbp, kind="sym", text="def foo(): pass\n// used in:",
                     file_path="src/a.py", symbol_name="foo", module="src",
                     line_start=1, line_end=1, commit_sha="sha1",
                     embedding=[1.0, 0.0])
    ci_db.upsert_sym(dbp, kind="arch", text="Module src handles things.",
                     file_path=None, symbol_name=None, module="src",
                     line_start=None, line_end=None, commit_sha="sha1",
                     embedding=[0.9, 0.1])
    out = ci_search.search_and_format(dbp, query_vec=[1.0, 0.0], sym_k=3, arch_k=2)
    assert "## Relevant code" in out
    assert "### Symbols" in out
    assert "foo" in out
    assert "### Modules" in out
    assert "src" in out


def test_format_empty_returns_empty_string(tmp_path):
    dbp = str(tmp_path / "ci.db")
    ci_db.init(dbp, dim=2)
    out = ci_search.search_and_format(dbp, query_vec=[1.0, 0.0], sym_k=3, arch_k=2)
    assert out == ""
