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
