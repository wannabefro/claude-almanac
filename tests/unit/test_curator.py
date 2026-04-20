"""Unit tests for the curator worker."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from claude_almanac.core import curator


def test_main_loads_config_and_invokes_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"message": {"role": "user", "content": "hi"}}),
                json.dumps({"message": {"role": "assistant", "content": "hello"}}),
            ]
        )
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_TRANSCRIPT", str(transcript))

    called = {"ran": False}
    monkeypatch.setattr(
        "claude_almanac.core.curator._run_llm",
        lambda *a, **kw: '{"decisions": [{"action": "archive_turn", "text": "x"}]}',
    )
    monkeypatch.setattr(
        "claude_almanac.core.curator._apply_decisions",
        lambda *a, **kw: called.update(ran=True),
    )
    curator.main()
    assert called["ran"] is True


def test_apply_decisions_redirects_on_dup(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    # stub dedup to always redirect
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: ("existing.md", 14.0),
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    snapshot_calls: list[dict] = []

    def _fake_snapshot(db, *, scope_dir, slug, new_text, new_kind, new_embedding, provenance):
        snapshot_calls.append({"slug": slug, "new_text": new_text, "provenance": provenance})
        # Simulate the file write so the path assertion works.
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / slug).write_text(new_text)

    monkeypatch.setattr(
        "claude_almanac.core.curator.versioning.snapshot_then_replace", _fake_snapshot
    )
    decisions = [
        {
            "action": "write_md",
            "scope": "global",
            "slug": "new.md",
            "kind": "project",
            "text": "body",
        }
    ]
    from claude_almanac.core import paths as p

    p.ensure_dirs()
    curator._apply_decisions(decisions)
    # File should be written under the redirected slug, not the original
    assert (p.global_memory_dir() / "existing.md").exists()
    assert not (p.global_memory_dir() / "new.md").exists()
    # Dedup redirect: provenance should be "dedup"
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["slug"] == "existing.md"
    assert snapshot_calls[0]["provenance"] == "dedup"


def test_apply_decisions_skips_identical_rewrite(monkeypatch, tmp_path):
    """Verify the curator delegates identical re-writes to snapshot_then_replace
    exactly once (routing-only test). The actual no-op body-match guard is
    tested in test_versioning.py::test_identical_rewrite_is_noop."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: ("existing.md", 0.0),
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    snapshot_calls: list[dict] = []

    def _fake_snapshot(db, *, scope_dir, slug, new_text, new_kind, new_embedding, provenance):
        # Simulate no-op: file already has identical content, don't overwrite.
        snapshot_calls.append({"slug": slug, "new_text": new_text})

    monkeypatch.setattr(
        "claude_almanac.core.curator.versioning.snapshot_then_replace", _fake_snapshot
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    # Seed the target file with the exact body we're about to "write" again.
    (p.global_memory_dir() / "existing.md").write_text("body identical")
    decisions = [
        {
            "action": "write_md",
            "scope": "global",
            "slug": "new.md",
            "kind": "project",
            "text": "body identical",
        }
    ]
    curator._apply_decisions(decisions)
    # snapshot_then_replace was called once — it owns the no-op check internally.
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["slug"] == "existing.md"
    # The file is still there, untouched (our fake snapshot didn't re-write it).
    assert (p.global_memory_dir() / "existing.md").read_text() == "body identical"


def test_apply_decisions_overwrites_on_paraphrase_after_redirect(monkeypatch, tmp_path):
    """A paraphrase redirect (same slug, different body) should still
    overwrite the md file via snapshot_then_replace."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: ("existing.md", 0.3),  # paraphrase distance
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    snapshot_calls: list[dict] = []

    def _fake_snapshot(db, *, scope_dir, slug, new_text, new_kind, new_embedding, provenance):
        snapshot_calls.append({"slug": slug, "new_text": new_text, "provenance": provenance})
        # Simulate the file write so path assertions work.
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / slug).write_text(new_text)

    monkeypatch.setattr(
        "claude_almanac.core.curator.versioning.snapshot_then_replace", _fake_snapshot
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    # Seed with *different* existing body so the paraphrase truly re-writes.
    (p.global_memory_dir() / "existing.md").write_text("original phrasing")
    decisions = [
        {
            "action": "write_md",
            "scope": "global",
            "slug": "new.md",
            "kind": "project",
            "text": "refined phrasing",
        }
    ]
    curator._apply_decisions(decisions)
    # snapshot_then_replace called once with the dedup slug + dedup provenance
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0]["slug"] == "existing.md"
    assert snapshot_calls[0]["provenance"] == "dedup"
    assert (p.global_memory_dir() / "existing.md").read_text() == "refined phrasing"


def test_parse_decisions_accepts_documented_envelope():
    out = curator._parse_decisions(
        '{"decisions": [{"action": "archive_turn", "text": "x"}]}'
    )
    assert out == [{"action": "archive_turn", "text": "x"}]


def test_parse_decisions_accepts_bare_list():
    out = curator._parse_decisions(
        '[{"action": "skip_all", "reason": "nothing durable"}]'
    )
    assert out == [{"action": "skip_all", "reason": "nothing durable"}]


def test_parse_decisions_strips_markdown_fence():
    out = curator._parse_decisions(
        '```json\n[{"action": "write_md", "slug": "a.md", "text": "x"}]\n```'
    )
    assert out == [{"action": "write_md", "slug": "a.md", "text": "x"}]


def test_parse_decisions_strips_fence_with_envelope():
    out = curator._parse_decisions(
        '```json\n{"decisions": [{"action": "archive_turn", "text": "y"}]}\n```'
    )
    assert out == [{"action": "archive_turn", "text": "y"}]


def test_parse_decisions_returns_empty_on_junk():
    assert curator._parse_decisions("not json at all") == []
    assert curator._parse_decisions("") == []
    assert curator._parse_decisions("   ") == []


def test_parse_decisions_returns_empty_on_unexpected_shape():
    # A bare string or number is legal JSON but has no decisions to extract.
    assert curator._parse_decisions('"just a string"') == []
    assert curator._parse_decisions("42") == []


def test_apply_decisions_accepts_prompt_shape_name_content_type(monkeypatch, tmp_path):
    """Haiku emits {action, name, content, type} per the prompt; the worker
    must route that to the same (slug, text, kind) path as the legacy shape."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: (None, 99.0),
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    snapshots: list[dict] = []

    def _capture_snapshot(db, *, scope_dir, slug, new_text, new_kind, new_embedding, provenance):
        snapshots.append({"slug": slug, "new_kind": new_kind, "provenance": provenance})
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / slug).write_text(new_text)

    monkeypatch.setattr(
        "claude_almanac.core.curator.versioning.snapshot_then_replace", _capture_snapshot
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    decisions = [
        {
            "action": "write_md",
            "type": "reference",
            "scope": "global",
            "name": "reference_xcode_select_git_workaround",
            "content": "Problem: xcode-select drift. Fix: DEVELOPER_DIR=...",
        }
    ]
    curator._apply_decisions(decisions)
    # File landed with the .md suffix auto-appended.
    assert (p.global_memory_dir() / "reference_xcode_select_git_workaround.md").exists()
    # snapshot_then_replace called with correct slug and kind.
    assert len(snapshots) == 1
    assert snapshots[0]["slug"] == "reference_xcode_select_git_workaround.md"
    assert snapshots[0]["new_kind"] == "reference"
    assert snapshots[0]["provenance"] == "write_md"


def test_apply_decisions_update_md_routes_through_write_path(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "claude_almanac.core.curator.dedup.find_dup_slug",
        lambda **kw: (None, 99.0),
    )
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)

    def _fake_snapshot(db, *, scope_dir, slug, new_text, new_kind, new_embedding, provenance):
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / slug).write_text(new_text)

    monkeypatch.setattr(
        "claude_almanac.core.curator.versioning.snapshot_then_replace", _fake_snapshot
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    # Pre-existing file — update_md should overwrite it in place via snapshot_then_replace.
    existing = p.global_memory_dir() / "project_foo.md"
    existing.write_text("old body")
    decisions = [
        {
            "action": "update_md",
            "type": "project",
            "scope": "global",
            "name": "project_foo",
            "content": "new body",
        }
    ]
    curator._apply_decisions(decisions)
    assert existing.read_text() == "new body"


def test_apply_decisions_insert_archive_maps_to_unpinned_archive_row(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **kw: fake_embedder
    )
    monkeypatch.setattr("claude_almanac.core.curator.archive.init", lambda *a, **kw: None)
    inserts: list[dict] = []
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry",
        lambda _db, **kw: inserts.append(kw) or 1,
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    decisions = [
        {
            "action": "insert_archive",
            "type": "archive",
            "scope": "project",
            "content": "one-off fact to embed for later semantic recall",
        }
    ]
    curator._apply_decisions(decisions)
    assert len(inserts) == 1
    assert inserts[0]["pinned"] is False
    assert inserts[0]["kind"] == "archive"


def test_existing_memory_titles_lists_both_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths as p
    g = p.global_memory_dir()
    g.mkdir(parents=True)
    (g / "user_profile.md").write_text("User is a Go developer.\nMore context below.")
    proj = p.project_memory_dir()
    proj.mkdir(parents=True)
    (proj / "project_foo.md").write_text("Active incident: deploys blocked.")
    out = curator._existing_memory_titles()
    assert "[global] user_profile" in out
    assert "Go developer" in out
    assert "[project] project_foo" in out
    assert "deploys blocked" in out


def test_existing_memory_titles_empty_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    out = curator._existing_memory_titles()
    assert "none" in out.lower()


def test_build_system_prompt_substitutes_existing_memories(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths as p
    g = p.global_memory_dir()
    g.mkdir(parents=True)
    (g / "user_profile.md").write_text("senior go dev")
    prompt = curator._build_system_prompt()
    # The placeholder is gone and replaced with the real content.
    assert "{{EXISTING_MEMORIES}}" not in prompt
    assert "user_profile" in prompt



def test_main_tolerates_bare_list_response(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"message": {"role": "user", "content": "hi"}}) + "\n"
    )
    monkeypatch.setenv("CLAUDE_ALMANAC_TRANSCRIPT", str(transcript))
    monkeypatch.setattr(
        "claude_almanac.core.curator._run_llm",
        lambda *a, **kw: '[{"action": "archive_turn", "text": "y"}]',
    )
    called = {"n": 0}

    def _count(decisions):
        called["n"] = len(decisions)

    monkeypatch.setattr("claude_almanac.core.curator._apply_decisions", _count)
    curator.main()
    assert called["n"] == 1


def test_run_llm_invokes_make_curator_with_system_and_tail(monkeypatch):
    """_run_llm should build the system prompt and delegate to make_curator(cfg).invoke(...)."""
    from claude_almanac.core import curator

    captured = {}

    class _FakeCurator:
        name = "fake"
        model = "fake-model"
        timeout_s = 1.0

        def invoke(self, system_prompt, user_turn):
            captured["system"] = system_prompt
            captured["user"] = user_turn
            return '[{"action": "skip_all"}]'

    monkeypatch.setattr(
        "claude_almanac.core.curator.make_curator",
        lambda cfg: _FakeCurator(),
    )
    out = curator._run_llm("TRANSCRIPT TAIL")
    assert out == '[{"action": "skip_all"}]'
    assert "EXISTING_MEMORIES" not in captured["system"]  # placeholder was substituted
    assert captured["user"] == "TRANSCRIPT TAIL"


def test_run_llm_swallows_provider_exceptions(monkeypatch, caplog):
    """If make_curator itself raises, _run_llm must not crash the Stop hook."""
    from claude_almanac.core import curator

    def _boom(cfg):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("claude_almanac.core.curator.make_curator", _boom)
    caplog.set_level("WARNING")
    out = curator._run_llm("tail")
    assert out == "{}"
    assert "provider" in caplog.text.lower() or "unavailable" in caplog.text.lower()


def test_apply_decisions_dedup_writes_history(tmp_path, monkeypatch):
    """When dedup redirects to an existing slug with different content, the
    prior body is snapshotted to entries_history with provenance='dedup'."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    from claude_almanac.core import config, curator, paths, versioning

    cfg = config.default_config()
    config.save(cfg)
    # Seed: write 'foo.md' with body-1 via the curator write path
    scope_dir = paths.project_memory_dir()
    scope_dir.mkdir(parents=True, exist_ok=True)
    db = scope_dir / "archive.db"

    class FakeEmbedder:
        name, model, dim, distance = "ollama", "bge-m3", 2, "l2"

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "claude_almanac.core.curator.make_embedder", lambda *a, **k: FakeEmbedder()
    )
    # Stub dedup: no dup on first call, redirect to seeded slug on second.
    calls = {"n": 0}

    def fake_find(db, embedding, threshold):
        calls["n"] += 1
        return (None, 1.0) if calls["n"] == 1 else ("foo.md", 0.1)

    monkeypatch.setattr(
        "claude_almanac.core.dedup.find_dup_slug",
        lambda *, db, embedding, threshold: fake_find(db, embedding, threshold),
    )
    # First decision: write_md body-1
    curator._apply_decisions([
        {"action": "write_md", "name": "foo", "content": "body-1", "type": "reference"},
    ])
    assert (scope_dir / "foo.md").read_text() == "body-1"
    # Second decision: write_md body-2 that dedups to foo.md
    curator._apply_decisions([
        {"action": "write_md", "name": "bar", "content": "body-2", "type": "reference"},
    ])
    chain = versioning.list_versions(db, slug="foo.md")
    assert chain[0].text == "body-2"
    assert chain[0].is_current is True
    assert chain[1].text == "body-1"
    assert chain[1].provenance == "dedup"
