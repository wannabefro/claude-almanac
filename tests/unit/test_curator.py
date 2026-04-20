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
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry", lambda *a, **kw: 1
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


def test_apply_decisions_skips_identical_rewrite(monkeypatch, tmp_path):
    """Re-extraction of a byte-identical memory on a subsequent Stop hook
    must NOT pile up new archive rows or re-write the md file."""
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
    insert_calls = {"n": 0}
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry",
        lambda *a, **kw: insert_calls.update(n=insert_calls["n"] + 1) or 1,
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
    assert insert_calls["n"] == 0  # no new archive row
    # The file is still there, untouched.
    assert (p.global_memory_dir() / "existing.md").read_text() == "body identical"


def test_apply_decisions_overwrites_on_paraphrase_after_redirect(monkeypatch, tmp_path):
    """A paraphrase redirect (same slug, different body) should still
    overwrite the md file AND add an archive row."""
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
    insert_calls = {"n": 0}
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry",
        lambda *a, **kw: insert_calls.update(n=insert_calls["n"] + 1) or 1,
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
    assert insert_calls["n"] == 1  # row inserted
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
    inserts: list[dict] = []

    def _capture_insert(_db, **kw):
        inserts.append(kw)
        return 1

    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry", _capture_insert
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
    # Archive row inserted with pinned=True and kind=reference.
    assert len(inserts) == 1
    assert inserts[0]["pinned"] is True
    assert inserts[0]["kind"] == "reference"
    assert inserts[0]["source"] == "md:reference_xcode_select_git_workaround.md"


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
    monkeypatch.setattr(
        "claude_almanac.core.curator.archive.insert_entry",
        lambda *a, **kw: 1,
    )
    from claude_almanac.core import paths as p
    p.ensure_dirs()
    # Pre-existing file — update_md should overwrite it in place.
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
