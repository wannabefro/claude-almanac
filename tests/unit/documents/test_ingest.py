"""Doc ingest walks configured globs, extracts chunks, upserts with kind='doc'."""
from __future__ import annotations

import sqlite3

import pytest

from claude_almanac.contentindex import db as cdb
from claude_almanac.documents import ingest


class _FakeEmbedder:
    """Deterministic embedder for ingest tests — embedding = hash-driven
    unit vector so rows are distinguishable but reproducible."""
    name = "fake"
    model = "fake"
    dim = 4
    distance = "l2"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = abs(hash(t)) % 1000
            out.append([h / 1000, (h * 2) % 1000 / 1000, 0.1, 0.1])
        return out


@pytest.fixture
def fixture_repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/architecture.md").write_text("# Arch\n\n## Memory\n\nm.\n")
    (tmp_path / "docs/ops.md").write_text("# Ops\n\nops body.\n")
    (tmp_path / "README.md").write_text("# Repo\n\nhello.\n")
    (tmp_path / "CHANGELOG.md").write_text("# Changes\n\n## 0.1\n\ntext.\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/main.py").write_text("def main(): pass\n")  # not a doc
    return tmp_path


def test_ingest_walks_default_patterns(fixture_repo, tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    emb = _FakeEmbedder()
    count = ingest.index_repo(
        repo_root=str(fixture_repo),
        db_path=dbp,
        embedder=emb,
        patterns=["docs/**", "README.md", "CHANGELOG.md"],
        excludes=[],
        chunk_max_chars=2000,
        chunk_overlap_chars=200,
        commit_sha="sha1",
    )
    assert count > 0
    conn = sqlite3.connect(dbp)
    rows = conn.execute(
        "SELECT file_path, symbol_name FROM entries WHERE kind='doc'"
    ).fetchall()
    paths = {r[0] for r in rows}
    names = {r[1] for r in rows}
    assert "docs/architecture.md" in paths
    assert "docs/ops.md" in paths
    assert "README.md" in paths
    assert "CHANGELOG.md" in paths
    assert "src/main.py" not in paths  # not a doc
    assert "Memory" in names  # level-2 heading from architecture.md
    assert "0.1" in names      # level-2 heading from CHANGELOG.md


def test_ingest_skips_excluded(fixture_repo, tmp_path):
    (fixture_repo / "docs/.output").mkdir()
    (fixture_repo / "docs/.output/generated.md").write_text("# Gen\n")
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    emb = _FakeEmbedder()
    ingest.index_repo(
        repo_root=str(fixture_repo), db_path=dbp, embedder=emb,
        patterns=["docs/**"], excludes=["**/.output/**"],
        chunk_max_chars=2000, chunk_overlap_chars=200,
        commit_sha="sha1",
    )
    conn = sqlite3.connect(dbp)
    paths = {r[0] for r in conn.execute(
        "SELECT file_path FROM entries WHERE kind='doc'"
    ).fetchall()}
    assert "docs/.output/generated.md" not in paths
    assert "docs/architecture.md" in paths


def test_ingest_logs_but_does_not_raise_on_embed_failure(
    fixture_repo, tmp_path, monkeypatch,
):
    """Embedder failures must not bubble out of index_repo — they must
    be logged (component=documents, event=doc.embed_fail) and the ingest
    must continue. Mirrors codeindex/sym.py's behavior so Task 8's
    dogfood run is debuggable if Ollama is down."""

    class _FailingEmbedder:
        name = "fake"
        model = "fake"
        dim = 4
        distance = "l2"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("boom: ollama down")

    # Route log_path (paths.logs_dir() -> data_dir()/logs) into tmp_path.
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "almanac"))

    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    # Should NOT raise — failure for every file is swallowed per-file.
    count = ingest.index_repo(
        repo_root=str(fixture_repo),
        db_path=dbp,
        embedder=_FailingEmbedder(),
        patterns=["docs/**"],
        excludes=[],
        chunk_max_chars=2000,
        chunk_overlap_chars=200,
        commit_sha="s",
    )
    assert count == 0  # every file failed

    # Zero rows inserted.
    conn = sqlite3.connect(dbp)
    rows = conn.execute("SELECT 1 FROM entries WHERE kind='doc'").fetchall()
    assert rows == []

    # Structured log captured the failure — at least one entry per failing file.
    log_file = tmp_path / "almanac" / "logs" / "content-index.log"
    assert log_file.exists(), "emit() should have created the log file"
    log_text = log_file.read_text()
    assert "event=doc.embed_fail" in log_text
    assert "component=documents" in log_text
    assert "docs/architecture.md" in log_text
    assert "boom: ollama down" in log_text


def test_module_field_is_posix_dirname(fixture_repo, tmp_path):
    dbp = str(tmp_path / "content.db")
    cdb.init(dbp, dim=4)
    ingest.index_repo(
        repo_root=str(fixture_repo), db_path=dbp, embedder=_FakeEmbedder(),
        patterns=["docs/**", "README.md"], excludes=[],
        chunk_max_chars=2000, chunk_overlap_chars=200, commit_sha="s",
    )
    conn = sqlite3.connect(dbp)
    modules = dict(conn.execute(
        "SELECT file_path, module FROM entries WHERE kind='doc'"
    ).fetchall())
    assert modules["docs/architecture.md"] == "docs"
    assert modules["README.md"] == ""
