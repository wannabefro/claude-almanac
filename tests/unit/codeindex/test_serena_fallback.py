from unittest.mock import patch

from claude_almanac.codeindex.extractors import serena_fallback


def test_extract_returns_empty_when_serena_unreachable(tmp_path):
    p = tmp_path / "a.rs"
    p.write_text("fn main() {}\n")
    # Simulate unreachable Serena by raising from the overview call
    with patch("claude_almanac.codeindex.serena_client.get_symbols_overview",
               side_effect=ConnectionError("refused")):
        assert serena_fallback.extract(str(p), "a.rs") == []


def test_extract_returns_empty_on_file_read_error(tmp_path):
    # Non-existent file — serena can't help and read will OSError
    with patch("claude_almanac.codeindex.serena_client.get_symbols_overview",
               return_value=[]):
        assert serena_fallback.extract(str(tmp_path / "missing.rs"), "missing.rs") == []


def test_extract_uses_overview_names_and_resolves_line(tmp_path):
    p = tmp_path / "a.rs"
    p.write_text("fn main() {}\nfn helper() {}\n")
    # Fake Serena SymbolRef objects with .name, .kind, .line_end
    class _S:
        def __init__(self, name, kind, line_end):
            self.name, self.kind, self.line_end = name, kind, line_end
    fakes = [_S("main", "function", 1), _S("helper", "function", 2)]
    with patch("claude_almanac.codeindex.serena_client.get_symbols_overview",
               return_value=fakes):
        refs = serena_fallback.extract(str(p), "a.rs")
    names = sorted(r.name for r in refs)
    assert names == ["helper", "main"]


def test_extract_line_end_zero_falls_back_to_line_start(tmp_path):
    # get_symbols_overview in production returns line_end=0 for symbols
    # whose body span it can't determine. The extractor must fall back to
    # the resolved line_start rather than emit a nonsensical 0.
    p = tmp_path / "a.rs"
    p.write_text("fn main() {}\nfn helper() {}\n")

    class _S:
        def __init__(self, name, kind, line_end):
            self.name, self.kind, self.line_end = name, kind, line_end

    fakes = [_S("helper", "function", 0)]
    with patch("claude_almanac.codeindex.serena_client.get_symbols_overview",
               return_value=fakes):
        refs = serena_fallback.extract(str(p), "a.rs")
    assert len(refs) == 1
    ref = refs[0]
    assert ref.name == "helper"
    assert ref.line_start == 2
    assert ref.line_end == ref.line_start
