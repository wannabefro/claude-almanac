"""End-to-end: seed a digest markdown file, ASGI-serve it via digest_server.app."""
from __future__ import annotations

import importlib
from datetime import date

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_digest_generate_then_serve_round_trip(isolated_data_dir, monkeypatch):
    # isolated_data_dir already sets CLAUDE_ALMANAC_DATA_DIR.
    # Import paths AFTER env is set so paths resolve correctly.
    from claude_almanac.core import paths

    digests = paths.digests_dir()
    digests.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    (digests / f"{today}.md").write_text("# Smoke digest\n\nbody\n")

    # Reload server so it picks up the new CLAUDE_ALMANAC_DATA_DIR.
    import claude_almanac.digest.server as digest_server
    importlib.reload(digest_server)

    client = TestClient(digest_server.app)
    r = client.get(f"/digest/{today}")
    assert r.status_code == 200
    assert "Smoke digest" in r.text
