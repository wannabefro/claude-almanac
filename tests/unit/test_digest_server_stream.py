import importlib

import pytest
from fastapi.testclient import TestClient

import claude_almanac.digest.server as server_mod


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    d = tmp_path / "digests"
    d.mkdir()
    (d / "2026-04-19.md").write_text("# d\n\ncontent\n")
    importlib.reload(server_mod)
    return TestClient(server_mod.app)


def test_ask_stream_emits_rendered_and_done(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "claude_almanac.digest.server.answer_question",
        lambda **kw: "hello **world**",
    )
    with client.stream(
        "POST",
        "/ask/stream?date=2026-04-19",
        data={"question": "why?", "mode": "fast"},
    ) as r:
        chunks = list(r.iter_text())
    body = "".join(chunks)
    assert "event: token" in body
    assert "event: rendered" in body
    assert "event: done" in body
    assert "hello" in body


def test_ask_stream_emits_error(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    def boom(**kw):
        raise RuntimeError("boom")
    monkeypatch.setattr("claude_almanac.digest.server.answer_question", boom)
    with client.stream(
        "POST",
        "/ask/stream?date=2026-04-19",
        data={"question": "why?", "mode": "fast"},
    ) as r:
        body = "".join(r.iter_text())
    assert "event: error" in body
    assert "boom" in body
