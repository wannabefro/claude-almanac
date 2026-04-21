from claude_almanac.codeindex import status as ci_status
from claude_almanac.contentindex import db as ci_db


def test_status_reports_missing_db(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    rc = ci_status.main(str(tmp_path))
    assert rc == 1
    assert "no content-index.db" in capsys.readouterr().out


def test_status_reports_counts_and_dirty(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    from claude_almanac.core import paths
    dbp = paths.project_memory_dir() / "content-index.db"
    dbp.parent.mkdir(parents=True, exist_ok=True)
    ci_db.init(str(dbp), dim=2)
    ci_db.upsert(str(dbp), kind="sym", text="x", file_path="a.py",
                     symbol_name="f", module="m",
                     line_start=1, line_end=1, commit_sha="sha1",
                     embedding=[1.0, 0.0])
    ci_db.mark_dirty(str(dbp), module="m", sha="sha1")
    rc = ci_status.main(str(tmp_path))
    assert rc == 0
    out = capsys.readouterr().out
    assert "sym=1" in out
    assert "arch=0" in out
    assert "dirty=1" in out
