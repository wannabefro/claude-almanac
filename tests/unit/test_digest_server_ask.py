import importlib

from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    d = tmp_path / "digests"
    d.mkdir()
    (d / "2026-04-19.md").write_text("# d\n\ncontent\n")
    importlib.reload(server_mod)
    return TestClient(server_mod.app)


def test_ask_fast_returns_html_fragment(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "claude_almanac.digest.server.answer_question",
        lambda **kw: "**bold answer**",
    )
    r = client.post(
        "/ask?date=2026-04-19",
        data={"question": "why?", "mode": "fast"},
    )
    assert r.status_code == 200
    assert "bold answer" in r.text
    assert "chat-turn" in r.text


def test_ask_returns_error_turn_on_exception(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    def boom(**kw):
        raise RuntimeError("no dice")
    monkeypatch.setattr("claude_almanac.digest.server.answer_question", boom)
    r = client.post(
        "/ask?date=2026-04-19",
        data={"question": "why?", "mode": "fast"},
    )
    assert r.status_code == 200
    assert "no dice" in r.text
