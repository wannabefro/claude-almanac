import pytest

from claude_almanac.digest.qa import registry


def test_tool_registers_and_builds_schema():
    r = registry.Registry()

    @r.tool("echo", "Echo input")
    def echo(text: str, n: int = 1) -> str:
        return text * n

    entry = r["echo"]
    assert entry.schema["input_schema"]["properties"]["text"] == {"type": "string"}
    assert entry.schema["input_schema"]["properties"]["n"] == {"type": "integer"}
    assert entry.schema["input_schema"]["required"] == ["text"]


def test_double_register_raises():
    r = registry.Registry()

    @r.tool("x", "x")
    def a() -> str: return "a"

    with pytest.raises(ValueError):
        @r.tool("x", "x2")
        def b() -> str: return "b"


@pytest.mark.skip(reason="requires B2 tool modules; un-skipped in Task B2")
def test_auto_discover_imports_tool_modules(monkeypatch):
    # Fresh registry to avoid polluting the module-level one.
    r = registry.Registry()
    registry.auto_discover("claude_almanac.digest.qa.tools", registry=r)
    names = {e.name for e in r.all()}
    assert "search_activity" in names
    assert "git_show" in names
