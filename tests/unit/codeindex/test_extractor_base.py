from claude_almanac.codeindex.extractors.base import SymbolRef


def test_symbolref_is_frozen():
    s = SymbolRef(name="f", kind="function", visibility="public",
                  line_start=1, line_end=5, signature="def f()")
    try:
        s.name = "g"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("SymbolRef should be frozen")


def test_symbolref_values():
    s = SymbolRef(name="Cls", kind="class", visibility="public",
                  line_start=10, line_end=20, signature="class Cls:")
    assert s.name == "Cls"
    assert s.kind == "class"
    assert s.visibility == "public"
    assert s.line_start == 10
    assert s.line_end == 20
