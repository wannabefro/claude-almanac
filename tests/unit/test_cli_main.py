import pytest

from claude_almanac.cli import main as cli_main


def test_main_no_args_prints_help(capsys):
    with pytest.raises(SystemExit):
        cli_main.main([])
    assert "usage:" in capsys.readouterr().out.lower()


def test_main_status_exits_ok(capsys, monkeypatch):
    monkeypatch.setattr("claude_almanac.cli.main.cmd_status", lambda _args: None)
    cli_main.main(["status"])


def test_main_unknown_exits_nonzero():
    with pytest.raises(SystemExit):
        cli_main.main(["nope"])
