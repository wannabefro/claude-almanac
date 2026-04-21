"""Run rollup generator across ollama + anthropic_sdk providers using the same
curator fixtures. Asserts both produce a parseable output with narrative +
decisions + artifacts when the model cooperates."""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from claude_almanac.core import archive, config, paths

pytestmark = pytest.mark.integration

# Reuse the curator transcript fixtures (four short .jsonl files).
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "transcripts"


def _discover_fixtures() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(FIXTURES_DIR.glob("*.jsonl"))


@pytest.mark.parametrize("provider", ["ollama", "anthropic_sdk"])
def test_rollup_generator_emits_valid_shape(
    provider: str,
    isolated_data_dir: Path,
) -> None:
    """Both providers produce a rollup with the correct top-level shape."""
    if provider == "anthropic_sdk" and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    # Note: "ollama" is already guarded by the session-scoped _require_ollama
    # fixture in conftest.py — no extra check needed here.

    fixtures = _discover_fixtures()
    if not fixtures:
        pytest.skip(f"No .jsonl fixtures found under {FIXTURES_DIR}")

    from claude_almanac.curators import make_curator
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile
    from claude_almanac.rollups.generator import RollupGenerator

    base_cfg = config.default_config()
    profile = get_profile("ollama", "bge-m3")

    # Set curator provider for this parametrize arm.
    curator_cfg = dataclasses.replace(
        base_cfg,
        curator=dataclasses.replace(base_cfg.curator, provider=provider),
    )

    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )

    embedder = make_embedder(base_cfg.embedder.provider, base_cfg.embedder.model)
    gen = RollupGenerator(
        curator=make_curator(curator_cfg),
        embedder=embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )

    # Run against the first fixture. If it works we've proven the provider path;
    # if the model returns non-JSON, skip rather than fail.
    fixture = fixtures[0]
    rollup = gen.generate(
        transcript_path=fixture,
        session_id=fixture.stem,
        repo_key="test",
        branch=None,
        trigger="explicit",
        min_turns=2,
    )

    if rollup is None:
        pytest.skip(
            f"{provider} produced unparseable output on {fixture.name} — "
            "model-quality gate, not a code regression"
        )

    # Shape assertions.
    assert rollup.narrative, f"{provider}: narrative must not be empty"
    assert isinstance(rollup.decisions, list), (
        f"{provider}: decisions must be a list, got {type(rollup.decisions)}"
    )
    assert isinstance(rollup.artifacts, dict), (
        f"{provider}: artifacts must be a dict, got {type(rollup.artifacts)}"
    )
    assert isinstance(rollup.embedding, list), (
        f"{provider}: embedding must be a list"
    )
    assert len(rollup.embedding) == profile.dim, (
        f"{provider}: embedding dim {len(rollup.embedding)} != expected {profile.dim}"
    )

    # artifacts must carry the three canonical keys (even if lists are empty).
    for key in ("files", "commits", "memories"):
        assert key in rollup.artifacts, (
            f"{provider}: rollup.artifacts missing key '{key}'; got {rollup.artifacts!r}"
        )


@pytest.mark.parametrize("provider", ["ollama", "anthropic_sdk"])
def test_rollup_generator_handles_short_transcript(
    provider: str,
    isolated_data_dir: Path,
    tmp_path: Path,
) -> None:
    """A transcript shorter than min_turns returns None without raising."""
    if provider == "anthropic_sdk" and not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from claude_almanac.curators import make_curator
    from claude_almanac.embedders import make_embedder
    from claude_almanac.embedders.profiles import get as get_profile
    from claude_almanac.rollups.generator import RollupGenerator

    base_cfg = config.default_config()
    profile = get_profile("ollama", "bge-m3")
    curator_cfg = dataclasses.replace(
        base_cfg,
        curator=dataclasses.replace(base_cfg.curator, provider=provider),
    )

    short_transcript = tmp_path / "short.jsonl"
    short_transcript.write_text(
        '{"type":"user","message":{"content":"hi"},"timestamp":1}\n'
    )

    paths.ensure_dirs()
    db = paths.project_memory_dir() / "archive.db"
    archive.init(
        db,
        embedder_name=profile.provider,
        model=profile.model,
        dim=profile.dim,
        distance=profile.distance,
    )

    embedder = make_embedder(base_cfg.embedder.provider, base_cfg.embedder.model)
    gen = RollupGenerator(
        curator=make_curator(curator_cfg),
        embedder=embedder,
        memories_for_window=lambda *a, **kw: [],
        git_commits_for_window=lambda *a, **kw: [],
    )

    result = gen.generate(
        transcript_path=short_transcript,
        session_id="too-short",
        repo_key="test",
        branch=None,
        trigger="explicit",
        min_turns=3,
    )
    assert result is None, (
        f"{provider}: expected None for transcript below min_turns, got {result!r}"
    )
