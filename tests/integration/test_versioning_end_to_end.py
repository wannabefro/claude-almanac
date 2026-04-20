"""End-to-end: run the curator path that writes two distinct bodies for the
same slug (via dedup redirect), then invoke recall history and assert the chain."""
from __future__ import annotations

from pathlib import Path

import pytest

from claude_almanac.core import config, curator, paths, versioning

pytestmark = pytest.mark.integration


def test_dedup_redirect_preserves_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    cfg = config.default_config()
    config.save(cfg)
    scope = paths.project_memory_dir()
    scope.mkdir(parents=True, exist_ok=True)
    db = scope / "archive.db"

    # Use the real embedder + dedup path — this is the integration
    curator._apply_decisions([
        {"action": "write_md", "name": "decay_notes",
         "content": "v1: ebbinghaus with beta=0.5", "type": "reference"},
    ])
    curator._apply_decisions([
        {"action": "write_md", "name": "decay_notes_alt",
         "content": "v2: ebbinghaus with beta=0.5, also band=0.1", "type": "reference"},
    ])

    chain = versioning.list_versions(db, slug="decay_notes.md")
    assert len(chain) == 2, f"expected v1 → v2 chain, got {chain!r}"
    assert chain[0].is_current and "band=0.1" in chain[0].text
    assert not chain[1].is_current and "v1" in chain[1].text
    assert chain[1].provenance == "dedup"
