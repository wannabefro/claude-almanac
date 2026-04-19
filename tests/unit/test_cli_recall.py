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
