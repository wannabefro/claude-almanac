import importlib

from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    (tmp_path / "digests").mkdir()
    importlib.reload(server_mod)
    return TestClient(server_mod.app)


def test_generate_form_renders(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.get("/generate")
    assert r.status_code == 200
    assert "Generate a custom digest" in r.text


def test_generate_post_redirects_to_new_digest(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    def fake_generate(**kw):
        return {
            "digest_path": str(tmp_path / "digests" / "2026-04-19.md"),
            "commits_inserted": 0, "pruned": 0, "notified": None,
        }
    monkeypatch.setattr(
        "claude_almanac.digest.server.generator.generate", fake_generate,
    )
    r = client.post(
        "/generate",
        data={"repo": "", "since_hours": "24", "date": "2026-04-19"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/digest/2026-04-19"


def test_generate_post_rejects_bad_date(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    r = client.post(
        "/generate",
        data={"repo": "", "since_hours": "24", "date": "bad"},
    )
    assert r.status_code == 422
