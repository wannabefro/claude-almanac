"""OllamaCurator unit tests using respx to mock /api/chat."""
from __future__ import annotations

import httpx
import respx

from claude_almanac.curators.ollama import OllamaCurator


def test_invoke_posts_expected_payload_and_returns_message_content() -> None:
    with respx.mock(base_url="http://127.0.0.1:11434") as m:
        route = m.post("/api/chat").mock(
            return_value=httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": '[{"action": "skip_all"}]'}},
            )
        )
        c = OllamaCurator(model="gemma3:4b", timeout_s=5, host="http://127.0.0.1:11434")
        out = c.invoke("SYSTEM", "USER TAIL")

    assert out == '[{"action": "skip_all"}]'
    assert route.called
    sent = route.calls.last.request
    import json as _j
    body = _j.loads(sent.content)
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    # v0.3.10: schema-constrained decoding (was format="json" pre-0.3.10).
    # Enforces valid JSON at token-gen time, preventing the unescaped-inner-quote
    # failure mode that slipped past format="json" on small models.
    assert isinstance(body["format"], dict)
    assert body["format"]["type"] == "object"
    assert "decisions" in body["format"]["properties"]
    assert body["options"]["temperature"] == 0
    assert body["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER TAIL"},
    ]


def test_invoke_returns_empty_on_timeout(caplog) -> None:
    with respx.mock(base_url="http://127.0.0.1:11434") as m:
        m.post("/api/chat").mock(side_effect=httpx.ConnectTimeout("slow"))
        c = OllamaCurator(model="gemma3:4b", timeout_s=1, host="http://127.0.0.1:11434")
        caplog.set_level("WARNING")
        out = c.invoke("s", "u")

    assert out == ""
    assert "timeout" in caplog.text.lower() or "connect" in caplog.text.lower()


def test_invoke_returns_empty_on_http_error(caplog) -> None:
    with respx.mock(base_url="http://127.0.0.1:11434") as m:
        m.post("/api/chat").mock(return_value=httpx.Response(500, text="boom"))
        c = OllamaCurator(model="gemma3:4b", timeout_s=1, host="http://127.0.0.1:11434")
        caplog.set_level("WARNING")
        out = c.invoke("s", "u")

    assert out == ""
    assert "500" in caplog.text or "status" in caplog.text.lower()


def test_host_defaults_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://example.test:9999")
    c = OllamaCurator(model="gemma3:4b")
    assert c.host == "http://example.test:9999"
