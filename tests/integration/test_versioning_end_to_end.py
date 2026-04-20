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
    if len(chain) != 2:
        # Diagnostic: if dedup didn't fire, the second write created a distinct
        # slug instead of redirecting. Surface both so failure is easy to diagnose.
        chain_alt = versioning.list_versions(db, slug="decay_notes_alt.md")
        raise AssertionError(
            f"Expected dedup redirect to decay_notes.md with 2-version chain, got chain={chain!r}. "
            f"If chain_alt is non-empty (decay_notes_alt={chain_alt!r}), "
            f"the test bodies may not cross bge-m3's 0.5 L2 dedup threshold (see profiles.py)."
        )
    assert chain[0].is_current, f"expected chain[0] is live; got {chain[0]!r}"
    assert chain[0].text == "v2: ebbinghaus with beta=0.5, also band=0.1", (
        f"expected v2 body on live row; got {chain[0].text!r}"
    )
    assert not chain[1].is_current, f"expected chain[1] historical; got {chain[1]!r}"
    assert chain[1].text == "v1: ebbinghaus with beta=0.5", (
        f"expected v1 body in history; got {chain[1].text!r}"
    )
    assert chain[1].provenance == "dedup", (
        f"expected provenance=dedup on snapshot; got {chain[1].provenance!r}"
    )
