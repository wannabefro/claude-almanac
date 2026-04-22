from unittest.mock import MagicMock

from claude_almanac.core import retrieve
from claude_almanac.core.archive import Hit


def test_retrieve_appends_code_block_when_gate_opens(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(data))
    fake_embedder = MagicMock()
    fake_embedder.name = "ollama"
    fake_embedder.model = "bge-m3"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    fake_embedder.embed.return_value = [[1.0, 0.0]]

    monkeypatch.setattr("claude_almanac.core.retrieve.make_embedder",
                        lambda *a, **kw: fake_embedder)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.search",
                        lambda db, **kw: [Hit(id=1, text="mem hit", kind="project",
                                              source="md:foo.md", pinned=True,
                                              created_at=0, distance=14.0)])
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.init", lambda *a, **kw: None)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.assert_compatible",
                        lambda *a, **kw: None)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.reinforce",
                        lambda *a, **kw: 0)
    monkeypatch.setattr(
        "claude_almanac.core.retrieve._codeindex_block",
        lambda *a, **kw: "## Relevant code\n- sym foo",
    )

    out = retrieve.run("where is `foo` defined in a.py?")
    assert "Relevant memories" in out
    assert "Relevant code" in out


def test_retrieve_appends_docs_block_when_present(monkeypatch, tmp_path):
    """The injected code block now carries a ### Docs sub-section when the
    content-index has doc rows matching the query."""
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(data))
    fake_embedder = MagicMock()
    fake_embedder.name = "ollama"
    fake_embedder.model = "bge-m3"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    fake_embedder.embed.return_value = [[1.0, 0.0]]

    monkeypatch.setattr("claude_almanac.core.retrieve.make_embedder",
                        lambda *a, **kw: fake_embedder)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.search",
                        lambda db, **kw: [])
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.init", lambda *a, **kw: None)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.assert_compatible",
                        lambda *a, **kw: None)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.reinforce",
                        lambda *a, **kw: 0)

    captured = {}

    def _fake_block(*args, **kwargs):
        captured.update(kwargs)
        return (
            "## Relevant code\n"
            "### Symbols\n- [sym] a.py:1-1  foo\n"
            "### Docs\n- [doc] docs/a.md:1-5 → Intro — body"
        )

    monkeypatch.setattr(
        "claude_almanac.core.retrieve._codeindex_block",
        _fake_block,
    )

    out = retrieve.run("where is foo defined in a.py?")
    assert "### Docs" in out
    assert "Intro" in out
    # The gate should have passed docs_autoinject=True (default) and a dict scoring.
    assert captured.get("docs_autoinject") is True
    assert isinstance(captured.get("scoring"), dict)
    assert "sym" in captured["scoring"]
    assert "doc" in captured["scoring"]


def test_retrieve_omits_code_block_when_gate_closed(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(data))
    fake_embedder = MagicMock()
    fake_embedder.name = "ollama"
    fake_embedder.model = "bge-m3"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    fake_embedder.embed.return_value = [[1.0, 0.0]]

    monkeypatch.setattr("claude_almanac.core.retrieve.make_embedder",
                        lambda *a, **kw: fake_embedder)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.search",
                        lambda db, **kw: [])
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.init", lambda *a, **kw: None)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.assert_compatible",
                        lambda *a, **kw: None)

    out = retrieve.run("vanilla english sentence with no code signals")
    assert "Relevant code" not in out
