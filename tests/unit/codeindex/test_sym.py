from unittest.mock import MagicMock

from claude_almanac.codeindex import sym
from claude_almanac.contentindex import db as ci_db


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
    # No header when path/module/kind/name kwargs aren't supplied.
    assert text.splitlines()[0] == "def foo():"
    assert "// used in:" in text
    assert "src/a.py:12" in text


def test_compose_text_no_refs():
    text = sym.compose_text("def foo():", [])
    # Bare signature only — no "used in" section without refs.
    assert text == "def foo():"


def test_compose_text_enriches_with_path_and_kind():
    """v0.3.8: file_rel + kind + name land in the embedded text so
    general-text embedders pick up path tokens for semantic queries."""
    text = sym.compose_text(
        "def ensure_schema(conn, *, profile):",
        [],
        file_rel="src/claude_almanac/core/archive.py",
        module="src/claude_almanac",
        kind="function",
        name="ensure_schema",
    )
    assert "src/claude_almanac/core/archive.py" in text
    assert "[function]" in text
    assert "ensure_schema" in text
    # Signature is still present
    assert "def ensure_schema(conn, *, profile):" in text
    # Header precedes signature
    lines = text.splitlines()
    assert lines[0].startswith("// ")
    assert lines[1] == "def ensure_schema(conn, *, profile):"
