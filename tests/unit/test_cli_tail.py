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


def test_tail_prefers_content_index_log_and_falls_back_to_legacy(
    tmp_path, monkeypatch, capsys
):
    """v0.4 renames code-index.log → content-index.log. `tail` reads
    the new path first and only falls back to the legacy name when the
    new file doesn't exist, so upgraded users can still see pre-upgrade
    entries without a wipe."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    logs = paths.logs_dir()
    logs.mkdir(parents=True)
    # Both files present: new path wins.
    (logs / "content-index.log").write_text(
        "2026-04-21 10:00:00 INFO new-location entry\n"
    )
    (logs / "code-index.log").write_text(
        "2026-04-20 10:00:00 INFO old-location entry\n"
    )
    cli_tail.run(["--no-follow", "--lines", "10", "--source", "code-index"])
    out = capsys.readouterr().out
    assert "new-location entry" in out
    assert "old-location entry" not in out


def test_tail_falls_back_to_legacy_log_when_new_missing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    logs = paths.logs_dir()
    logs.mkdir(parents=True)
    # Only legacy file exists — pre-upgrade user.
    (logs / "code-index.log").write_text(
        "2026-04-20 10:00:00 INFO legacy-only entry\n"
    )
    cli_tail.run(["--no-follow", "--lines", "10", "--source", "code-index"])
    out = capsys.readouterr().out
    assert "legacy-only entry" in out


def test_tail_content_index_source_alias_works(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    from claude_almanac.core import paths
    logs = paths.logs_dir()
    logs.mkdir(parents=True)
    (logs / "content-index.log").write_text(
        "2026-04-21 10:00:00 INFO content-indexed\n"
    )
    # `--source content-index` is an alias for the same source.
    cli_tail.run(["--no-follow", "--lines", "10", "--source", "content-index"])
    out = capsys.readouterr().out
    assert "content-indexed" in out
