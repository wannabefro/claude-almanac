from unittest.mock import MagicMock

from claude_almanac.cli import recall as cli_recall


def test_search_calls_archive(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.0, 1.0]]
    fake_embedder.name = "ollama"
    fake_embedder.dim = 2
    fake_embedder.distance = "l2"
    monkeypatch.setattr(
        "claude_almanac.cli.recall.make_embedder", lambda *a, **kw: fake_embedder
    )
    from claude_almanac.core.archive import Hit
    monkeypatch.setattr(
        "claude_almanac.cli.recall.archive.init", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "claude_almanac.cli.recall.archive.search",
        lambda db, **kw: [
            Hit(id=1, text="a match", kind="project", source="md:x.md",
                pinned=True, created_at=0, distance=14.0)
        ],
    )
    cli_recall.run(["search", "query"])
    out = capsys.readouterr().out
    assert "a match" in out
    assert "md:x.md" in out


def test_list_scans_md_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    g = tmp_path / "global"
    g.mkdir(parents=True)
    (g / "user_test.md").write_text("---\nname: test\n---\nbody")
    cli_recall.run(["list"])
    assert "user_test.md" in capsys.readouterr().out


def test_no_args_prints_usage(capsys):
    cli_recall.run([])
    assert "Usage" in capsys.readouterr().out


def _seed_project_db(tmp_path, slug: str, pinned: bool = False):
    """Seed the per-project archive with one entry at md:<slug>."""
    import os
    os.environ["CLAUDE_ALMANAC_DATA_DIR"] = str(tmp_path)
    from claude_almanac.core import archive, paths
    db = paths.project_memory_dir() / "archive.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    rowid = archive.insert_entry(
        db, text="t", kind="note", source=f"md:{slug}",
        pinned=pinned, embedding=[0.0, 1.0],
    )
    return db, rowid


def test_recall_pin_by_slug_sets_pinned_true(tmp_path, monkeypatch, capsys):
    db, _ = _seed_project_db(tmp_path, "project_foo.md", pinned=False)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    cli_recall.run(["pin", "project_foo.md"])
    from claude_almanac.core import archive
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert hits[0].pinned is True
    assert "pinned" in capsys.readouterr().out.lower()


def test_recall_pin_by_rowid_sets_pinned_true(tmp_path, monkeypatch, capsys):
    db, rowid = _seed_project_db(tmp_path, "project_foo.md", pinned=False)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    cli_recall.run(["pin", str(rowid)])
    from claude_almanac.core import archive
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert hits[0].pinned is True


def test_recall_unpin_by_slug_sets_pinned_false(tmp_path, monkeypatch, capsys):
    db, _ = _seed_project_db(tmp_path, "project_foo.md", pinned=True)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    cli_recall.run(["unpin", "project_foo.md"])
    from claude_almanac.core import archive
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert hits[0].pinned is False


def test_recall_pin_no_match_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli_recall.run(["pin", "ghost.md"])
    assert exc.value.code == 1


def test_recall_forget_moves_md_to_trash_and_deletes_archive_row(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import archive, paths
    scope = paths.project_memory_dir()
    scope.mkdir(parents=True)
    (scope / "project_drop.md").write_text("---\nname: drop\n---\nbody")
    db = scope / "archive.db"
    archive.init(db, embedder_name="ollama", model="bge-m3", dim=2, distance="l2")
    archive.insert_entry(
        db, text="drop", kind="note", source="md:project_drop.md",
        pinned=False, embedding=[0.0, 1.0],
    )
    cli_recall.run(["forget", "project_drop.md"])
    assert not (scope / "project_drop.md").exists()
    trash_entries = list((scope / "trash").glob("project_drop.md.*"))
    assert len(trash_entries) == 1
    hits = archive.search(db, query_embedding=[0.0, 1.0], top_k=5)
    assert hits == []


def test_recall_forget_ambiguous_slug_requires_scope(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    for scope in (paths.global_memory_dir(), paths.project_memory_dir()):
        scope.mkdir(parents=True)
        (scope / "user_x.md").write_text("body")
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli_recall.run(["forget", "user_x.md"])
    assert exc.value.code == 2
    assert "--scope" in capsys.readouterr().err


def test_recall_forget_with_scope_flag_picks_one_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    for scope in (paths.global_memory_dir(), paths.project_memory_dir()):
        scope.mkdir(parents=True)
        (scope / "user_x.md").write_text("body")
    cli_recall.run(["forget", "user_x.md", "--scope", "global"])
    assert not (paths.global_memory_dir() / "user_x.md").exists()
    assert (paths.project_memory_dir() / "user_x.md").exists()


def test_recall_export_default_path_concatenates_global_and_project(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from claude_almanac.core import paths
    g = paths.global_memory_dir()
    g.mkdir(parents=True)
    p = paths.project_memory_dir()
    p.mkdir(parents=True)
    (g / "user_profile.md").write_text("global body")
    (p / "project_state.md").write_text("project body")
    cli_recall.run(["export"])
    exports = list(tmp_path.glob("claude-almanac-export-*.md"))
    assert len(exports) == 1
    body = exports[0].read_text()
    assert "# global/user_profile.md" in body
    assert "global body" in body
    assert "# project/project_state.md" in body
    assert "project body" in body


def test_recall_export_custom_path_and_scope_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    g = paths.global_memory_dir()
    g.mkdir(parents=True)
    p = paths.project_memory_dir()
    p.mkdir(parents=True)
    (g / "user_a.md").write_text("A")
    (p / "project_b.md").write_text("B")
    out = tmp_path / "dump.md"
    cli_recall.run(["export", str(out), "--global"])
    text = out.read_text()
    assert "user_a.md" in text
    assert "project_b.md" not in text


def test_recall_export_all_scans_all_project_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    g = paths.global_memory_dir()
    g.mkdir(parents=True)
    (g / "user_a.md").write_text("A")
    proj_root = paths.projects_memory_dir()
    (proj_root / "git-aaaa1111").mkdir(parents=True)
    (proj_root / "git-aaaa1111" / "project_p1.md").write_text("P1")
    (proj_root / "git-bbbb2222").mkdir(parents=True)
    (proj_root / "git-bbbb2222" / "project_p2.md").write_text("P2")
    out = tmp_path / "all.md"
    cli_recall.run(["export", str(out), "--all"])
    text = out.read_text()
    assert "project_p1.md" in text
    assert "project_p2.md" in text
