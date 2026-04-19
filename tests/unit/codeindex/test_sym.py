from unittest.mock import MagicMock

from claude_almanac.codeindex import db as ci_db
from claude_almanac.codeindex import sym
from claude_almanac.codeindex.extractors.base import SymbolRef


def _fake_embedder(dim=2):
    e = MagicMock()
    e.embed.side_effect = lambda texts: [[1.0] * dim for _ in texts]
    return e


def test_extract_file_writes_only_public(tmp_path, monkeypatch):
    p = tmp_path / "a.py"
    p.write_text("def pub(): pass\ndef _priv(): pass\n")
    dbp = str(tmp_path / "ci.db")
    ci_db.init(dbp, dim=2)
    written = sym.extract_file(
        db_path=dbp, repo_root=str(tmp_path), module="mod",
        file_abs=str(p), commit_sha="sha1", embedder=_fake_embedder(),
    )
    assert written == 1
    results = ci_db.search(dbp, embedding=[1.0, 1.0], k=5, kind="sym")
    assert [r["symbol_name"] for r in results] == ["pub"]


def test_extract_file_skips_unknown_extension(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# heading\n")
    dbp = str(tmp_path / "ci.db")
    ci_db.init(dbp, dim=2)
    assert sym.extract_file(
        db_path=dbp, repo_root=str(tmp_path), module="mod",
        file_abs=str(p), commit_sha="sha1", embedder=_fake_embedder(),
    ) == 0


def test_extract_file_handles_empty_extractor_result(tmp_path):
    p = tmp_path / "__init__.py"
    p.write_text("")
    dbp = str(tmp_path / "ci.db")
    ci_db.init(dbp, dim=2)
    assert sym.extract_file(
        db_path=dbp, repo_root=str(tmp_path), module="mod",
        file_abs=str(p), commit_sha="sha1", embedder=_fake_embedder(),
    ) == 0


def test_compose_text_format():
    class _Ref:
        file_rel = "src/a.py"
        line = 12
        snippet = "call_site"
    text = sym.compose_text("def foo():", [_Ref()])
    assert text.splitlines()[0] == "def foo():"
    assert "// used in:" in text
    assert "src/a.py:12" in text


def test_compose_text_no_refs():
    text = sym.compose_text("def foo():", [])
    assert text.splitlines()[0] == "def foo():"
    assert "// used in:" in text
    # no ref lines follow
    assert len(text.splitlines()) == 3  # sig, blank, header
