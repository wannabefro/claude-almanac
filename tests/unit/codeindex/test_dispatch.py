from unittest.mock import patch

from claude_almanac.codeindex.extractors import extract_symbols
from claude_almanac.codeindex.extractors.base import SymbolRef


def test_python_file_uses_ast(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def foo(): pass\n")
    syms = extract_symbols(str(p), "m.py", str(tmp_path))
    assert [s.name for s in syms] == ["foo"]


def test_ts_file_uses_regex(tmp_path):
    p = tmp_path / "m.ts"
    p.write_text("export function bar() {}\n")
    syms = extract_symbols(str(p), "m.ts", str(tmp_path))
    assert [s.name for s in syms] == ["bar"]


def test_unknown_extension_tries_serena(tmp_path):
    p = tmp_path / "m.rs"
    p.write_text("fn main() {}\n")
    fake = [SymbolRef(name="main", kind="function", visibility="public",
                      line_start=1, line_end=1, signature="fn main() {}")]
    with patch("claude_almanac.codeindex.extractors.dispatch._sf.extract",
               return_value=fake):
        syms = extract_symbols(str(p), "m.rs", str(tmp_path))
    assert [s.name for s in syms] == ["main"]


def test_fast_path_exception_falls_through_to_serena(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def foo(): pass\n")
    fake = [SymbolRef(name="from_serena", kind="function", visibility="public",
                      line_start=1, line_end=1, signature="fn")]
    with patch("claude_almanac.codeindex.extractors.dispatch._py.extract",
               side_effect=RuntimeError("boom")), \
         patch("claude_almanac.codeindex.extractors.dispatch._sf.extract",
               return_value=fake):
        syms = extract_symbols(str(p), "m.py", str(tmp_path))
    assert [s.name for s in syms] == ["from_serena"]


def test_empty_fast_path_is_trusted(tmp_path):
    """An empty __init__.py should NOT fall through to Serena."""
    p = tmp_path / "__init__.py"
    p.write_text("")
    with patch("claude_almanac.codeindex.extractors.dispatch._sf.extract") as mock_sf:
        syms = extract_symbols(str(p), "__init__.py", str(tmp_path))
    assert syms == []
    mock_sf.assert_not_called()
