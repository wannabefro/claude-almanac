import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seeded_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core.archive import init
    from claude_almanac.core.paths import project_memory_dir
    from claude_almanac.embedders.profiles import get
    project_memory_dir().mkdir(parents=True, exist_ok=True)
    db = project_memory_dir() / "archive.db"
    profile = get("ollama", "bge-m3")
    init(db, embedder_name=profile.provider, model=profile.model,
         dim=profile.dim, distance=profile.distance)
    # Seed a rollup
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO rollups (session_id, repo_key, started_at, ended_at,"
            " turn_count, trigger, narrative, decisions, artifacts, created_at)"
            " VALUES ('s1', 'r', 1, 2, 5, 'session_end',"
            " 'We debugged auth flow.', '[]', '{}', 100)"
        )
        conn.commit()
    finally:
        conn.close()

    # Reimport / rebuild the FastAPI app with the fresh XDG dir
    import importlib

    import claude_almanac.digest.server as server_mod
    importlib.reload(server_mod)
    return TestClient(server_mod.app)


def test_rollups_index_returns_200(seeded_client):
    response = seeded_client.get("/rollups")
    assert response.status_code == 200
    assert "debugged" in response.text or "Rollup" in response.text


def test_rollup_detail_returns_200_when_present(seeded_client):
    # Rollup id is the first PK, likely 1
    response = seeded_client.get("/rollup/1")
    assert response.status_code == 200
    assert "debugged" in response.text


def test_rollup_detail_404_when_missing(seeded_client):
    response = seeded_client.get("/rollup/9999")
    assert response.status_code == 404
