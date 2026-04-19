from claude_almanac.codeindex.extractors import regex_tuned


def _write(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body)
    return str(path)


def test_ts_exported_function(tmp_path):
    p = _write(tmp_path, "a.ts", "export function foo() {\n  return 1;\n}\n")
    [s] = regex_tuned.extract(p, "a.ts")
    assert s.name == "foo"
    assert s.visibility == "public"
    assert s.kind == "function"
    assert s.line_start >= 1
    assert s.line_end >= s.line_start


def test_ts_private_const(tmp_path):
    p = _write(tmp_path, "a.ts", "const X = 1;\n")
    [s] = regex_tuned.extract(p, "a.ts")
    assert s.visibility == "private"


def test_go_uppercase_public(tmp_path):
    p = _write(tmp_path, "a.go", "func DoThing() {}\nfunc doThing() {}\n")
    by_name = {s.name: s.visibility for s in regex_tuned.extract(p, "a.go")}
    assert by_name["DoThing"] == "public"
    assert by_name["doThing"] == "private"


def test_java_public_class(tmp_path):
    p = _write(tmp_path, "A.java",
               "public class A {\n  public int m() { return 1; }\n}\n")
    by_name = {s.name: s.visibility for s in regex_tuned.extract(p, "A.java")}
    assert by_name.get("A") == "public"


def test_unknown_extension_returns_empty(tmp_path):
    p = _write(tmp_path, "a.rs", "fn x() {}\n")
    assert regex_tuned.extract(p, "a.rs") == []


def test_binary_guard(tmp_path):
    p = tmp_path / "a.ts"
    p.write_bytes(b"\x00" * 600 + b"export function foo() {}")
    assert regex_tuned.extract(str(p), "a.ts") == []
