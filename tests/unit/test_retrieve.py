from unittest.mock import MagicMock

import pytest

from claude_almanac.core import retrieve
from claude_almanac.core.archive import Hit


def test_format_hits_produces_relevant_memories_block():
    hits = [
        Hit(id=1, text="memory A", kind="project", source="md:foo.md",
            pinned=True, created_at=0, distance=14.0),
        Hit(id=2, text="memory B", kind="feedback", source="md:bar.md",
            pinned=True, created_at=0, distance=15.2),
    ]
    out = retrieve.format_hits(hits)
    assert "## Relevant memories" in out
    assert "md:foo.md" in out
    assert "memory A" in out
    assert "[project]" in out


def test_format_hits_empty_returns_empty_string():
    assert retrieve.format_hits([]) == ""


def test_run_retrieves_from_global_and_project(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(data))

    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[1.0, 0.0]]
    monkeypatch.setattr(
        "claude_almanac.core.retrieve.make_embedder",
        lambda *a, **kw: fake_embedder,
    )

    # Stub archive.search to return canned hits from two DBs
    calls = []

    def fake_search(db, *, query_embedding, top_k):
        calls.append(db)
        return [Hit(id=1, text=f"hit-from-{db.parent.name}",
                    kind="project", source="md:x.md", pinned=True,
                    created_at=0, distance=14.0)]

    monkeypatch.setattr("claude_almanac.core.retrieve.archive.search", fake_search)
    monkeypatch.setattr("claude_almanac.core.retrieve.archive.init", lambda *a, **kw: None)

    prompt = "what did we decide about X?"
    out = retrieve.run(prompt)
    assert "Relevant memories" in out
    # Ensure both scopes were searched
    assert len(calls) == 2


def test_run_raises_on_embedder_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import archive, paths, retrieve
    paths.ensure_dirs()
    # Seed a DB at the global path with ollama/bge-m3
    db = paths.global_memory_dir() / "archive.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=4, distance="l2")
    # Configure retrieve to use a different embedder
    from unittest.mock import MagicMock
    fake = MagicMock()
    fake.name = "openai"
    fake.model = "text-embedding-3-small"
    fake.dim = 1536
    fake.distance = "cosine"
    fake.embed.return_value = [[0.0] * 1536]
    monkeypatch.setattr("claude_almanac.core.retrieve.make_embedder",
                        lambda *a, **kw: fake)
    with pytest.raises(archive.EmbedderMismatch):
        retrieve.run("hi")
