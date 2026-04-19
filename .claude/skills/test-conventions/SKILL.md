---
name: test-conventions
description: TDD patterns used by claude-almanac — embedder mocking, archive integration fixtures, importlib.reload for server tests, XDG env overrides for path tests. Use when writing or modifying tests under `tests/`, especially for embedders, archive, server, or paths.
---

# test-conventions

claude-almanac's test suite follows a "mock-for-logic, integration-for-plumbing" split with a small number of reusable patterns. Follow these so new tests stay consistent.

## Unit vs. integration

- `tests/unit/` — default target; runs on every PR. Mocks external I/O (HTTP, subprocess, filesystem where practical). Run via `pytest tests/unit -v`.
- `tests/integration/` — requires live services (Ollama + bge-m3, SQLite file I/O); marked `@pytest.mark.integration`. Skipped by default via `pyproject.toml` `addopts = "-m 'not integration'"`. Run via `pytest -m integration -v`.

## Pattern: embedder mocking

For adapters using `httpx`, use `respx`:

```python
import respx
import httpx

@respx.mock
def test_ollama_embed_happy_path():
    respx.post("http://127.0.0.1:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1] * 1024})
    )
    e = OllamaEmbedder(model="bge-m3")
    assert len(e.embed(["hello"])[0]) == 1024
```

For adapters using vendor SDKs, use `unittest.mock.patch`:

```python
from unittest.mock import patch, MagicMock

def test_openai_embed():
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1] * 1536)]
    with patch("claude_almanac.embedders.openai.OpenAI", return_value=mock_client):
        e = OpenAIEmbedder(model="text-embedding-3-small")
        assert len(e.embed(["hi"])[0]) == 1536
```

## Pattern: archive integration via `core.archive.init`

Integration tests for the archive DB use a tmp-path fixture and `archive.init` to create a fresh DB:

```python
from claude_almanac.core import archive

@pytest.mark.integration
def test_archive_roundtrip(tmp_path, ollama_embedder):
    db = archive.init(tmp_path / "archive.db", embedder=ollama_embedder)
    archive.insert(db, scope="project", content="hello world", vector=ollama_embedder.embed(["hello world"])[0])
    hits = archive.search(db, query_vec=ollama_embedder.embed(["hello"])[0], top_k=5)
    assert len(hits) == 1
```

Never reuse a DB file across tests — `archive.init` stamps embedder metadata into `meta`, and a stale file trips `EmbedderMismatch`.

## Pattern: `importlib.reload` for server tests

`digest/server.py` configures FastAPI routes at import time using module-level config lookups. Tests that need to exercise config overrides (e.g. different `digest.hour` or feature flags) must reload the module after patching env / config:

```python
import importlib
from claude_almanac.digest import server

def test_server_respects_config_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DIGEST_HOUR", "9")
    importlib.reload(server)
    assert server.settings.digest_hour == 9
```

Without the reload, the server module uses the cached config from the first import and the test is meaningless.

## Pattern: XDG env overrides for path tests

All tests that touch `core/paths.py` override `CLAUDE_ALMANAC_DATA_DIR` / `CLAUDE_ALMANAC_CONFIG_DIR` via `monkeypatch`:

```python
def test_data_dir_respects_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    from claude_almanac.core import paths
    assert paths.data_dir() == tmp_path / "data"
```

Never rely on the default XDG location in tests — it pollutes the developer's real data dir. If a test fails to clean up, the next real session sees stale artifacts.

## Pattern: calibration corpus fixture

`tests/fixtures/calibration_corpus.jsonl` is shared across embedder calibration tests. Each line is `{"text_a": "...", "text_b": "...", "is_duplicate": true|false}`. When adding a new embedder, don't extend the corpus — use it as-is so cross-embedder thresholds are comparable.

## TDD rhythm

1. Write the failing test first for any new branching logic (thresholds, gates, dispatch).
2. Confirm red (`pytest -x` stops on the failure).
3. Implement the minimal change to go green.
4. Refactor if needed; tests stay green.
5. Commit the test + implementation together; do not land implementation-only commits for logic changes.

Plumbing code (I/O wiring, template rendering, subprocess shell-outs) may land with implementation + mock-based test in the same commit without a red-first step.
