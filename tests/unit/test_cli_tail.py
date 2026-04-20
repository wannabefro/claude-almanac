from claude_almanac.cli import tail as cli_tail


def test_tail_merges_two_logs_by_timestamp(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    logs = paths.logs_dir()
    logs.mkdir(parents=True)
    (logs / "curator.log").write_text(
        "2026-04-20 10:00:00 INFO curator start\n"
        "2026-04-20 10:00:05 INFO curator wrote 2 memories\n"
    )
    (logs / "code-index.log").write_text(
        "2026-04-20 10:00:02 INFO codeindex refresh begin\n"
        "2026-04-20 10:00:10 INFO codeindex refresh done\n"
    )
    cli_tail.run(["--no-follow", "--lines", "10"])
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 4
    assert "curator" in lines[0]
    assert "code-index" in lines[1]
    assert "curator" in lines[2]
    assert "code-index" in lines[3]


def test_tail_continuation_lines_inherit_previous_timestamp(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    logs = paths.logs_dir()
    logs.mkdir(parents=True)
    (logs / "curator.log").write_text(
        "2026-04-20 10:00:00 ERROR boom\n"
        "  Traceback (most recent call last):\n"
        "    File x.py, line 1\n"
        "2026-04-20 10:00:05 INFO recovered\n"
    )
    cli_tail.run(["--no-follow", "--lines", "10", "--source", "curator"])
    out = capsys.readouterr().out
    assert "cont" in out
    assert "Traceback" in out
