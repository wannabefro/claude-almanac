"""Shared integration fixtures. Tests here require live Ollama + bge-m3."""
from __future__ import annotations

import os

import pytest


def _ollama_reachable() -> bool:
    from urllib.error import URLError
    from urllib.request import urlopen
    endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        with urlopen(f"{endpoint.rstrip('/')}/api/version", timeout=2) as r:
            return r.status == 200
    except (URLError, TimeoutError, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_ollama():
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable; integration tests skipped")


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "data").mkdir()
    (tmp_path / "cfg").mkdir()
    return tmp_path
