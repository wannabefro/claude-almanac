from claude_almanac.codeindex.extractors import python_ast


def _write(tmp_path, body: str):
    path = tmp_path / "m.py"
    path.write_text(body)
    return str(path)


def test_extracts_public_function(tmp_path):
    p = _write(tmp_path, "def foo(x):\n    return x\n")
    syms = python_ast.extract(p, "m.py")
    assert len(syms) == 1
    assert syms[0].name == "foo"
    assert syms[0].visibility == "public"
    assert syms[0].kind == "function"
    assert syms[0].line_start >= 1
    assert syms[0].line_end >= syms[0].line_start


def test_underscore_prefix_is_private(tmp_path):
    p = _write(tmp_path, "def _helper():\n    pass\n")
    [s] = python_ast.extract(p, "m.py")
    assert s.visibility == "private"


def test_dunder_all_overrides_underscore(tmp_path):
    p = _write(tmp_path, "__all__ = ['_exported']\n\ndef _exported():\n    pass\n\ndef public():\n    pass\n")
    syms = {s.name: s.visibility for s in python_ast.extract(p, "m.py")}
    assert syms["_exported"] == "public"
    assert syms["public"] == "private"  # not in __all__


def test_class_and_uppercase_constant(tmp_path):
    p = _write(tmp_path, "class C:\n    pass\n\nCONST = 1\n")
    names = {s.name: s.kind for s in python_ast.extract(p, "m.py")}
    assert names["C"] == "class"
    assert names["CONST"] == "variable"


def test_syntax_error_returns_empty(tmp_path):
    p = _write(tmp_path, "def broken(\n")
    assert python_ast.extract(p, "m.py") == []
