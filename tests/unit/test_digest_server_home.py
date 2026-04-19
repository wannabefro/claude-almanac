import importlib

from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def test_home_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    (tmp_path / "digests").mkdir()
    importlib.reload(server_mod)
    client = TestClient(server_mod.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "no digests yet" in r.text


def test_home_shows_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    d = tmp_path / "digests"
    d.mkdir()
    (d / "2026-04-19.md").write_text("# digest\n\nSome content.\n")
    (d / "2026-04-18_r.md").write_text("# r digest\n\nrepo stuff.\n")
    importlib.reload(server_mod)
    client = TestClient(server_mod.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "2026-04-19" in r.text
    assert "r" in r.text
