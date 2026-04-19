import importlib

from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def test_health_reports_ok_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    (tmp_path / "digests").mkdir()
    importlib.reload(server_mod)
    client = TestClient(server_mod.app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"digest_dir_ok", "activity_db_ok", "claude_cli_ok"}
    assert body["digest_dir_ok"] is True
    assert body["activity_db_ok"] is False  # no DB yet
