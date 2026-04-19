import importlib

from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    d = tmp_path / "digests"
    d.mkdir()
    (d / "2026-04-19.md").write_text("# Daily digest — 2026-04-19\n\nhello\n")
    (d / "2026-04-19_r1.md").write_text("# r1 digest\n\nrepo\n")
    importlib.reload(server_mod)
    return TestClient(server_mod.app)


def test_digests_history_page(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digests")
    assert r.status_code == 200
    assert "2026-04-19" in r.text
    assert "r1" in r.text


def test_digest_by_date(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digest/2026-04-19")
    assert r.status_code == 200
    assert "Daily digest" in r.text


def test_digest_by_repo_and_date(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digest/r1/2026-04-19")
    assert r.status_code == 200
    assert "r1 digest" in r.text


def test_digest_404_on_missing(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digest/2024-01-01")
    assert r.status_code == 404


def test_digest_rejects_bad_date(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digest/NOTADATE")
    assert r.status_code == 404


def test_digest_rejects_path_traversal_repo(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/digest/..%2Fetc/2026-04-19")
    assert r.status_code == 404
