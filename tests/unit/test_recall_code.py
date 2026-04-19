from unittest.mock import MagicMock, patch

from claude_almanac.cli import recall


def test_recall_code_prints_hits(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    from claude_almanac.core import paths
    from claude_almanac.codeindex import db as ci_db
    dbp = paths.project_memory_dir() / "code-index.db"
    dbp.parent.mkdir(parents=True, exist_ok=True)
    ci_db.init(str(dbp), dim=2)
    ci_db.upsert_sym(str(dbp), kind="sym", text="def foo(): pass\n",
                     file_path="src/a.py", symbol_name="foo", module="src",
                     line_start=1, line_end=1, commit_sha="sha1",
                     embedding=[1.0, 0.0])

    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[1.0, 0.0]]
    with patch("claude_almanac.cli.recall.make_embedder",
               return_value=fake_embedder):
        recall.run(["code", "foo"])
    out = capsys.readouterr().out
    assert "foo" in out
    assert "src/a.py" in out


def test_recall_code_no_db_message(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    recall.run(["code", "anything"])
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "no code-index" in out.lower()
