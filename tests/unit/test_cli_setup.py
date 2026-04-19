from unittest.mock import MagicMock
from claude_almanac.cli import setup as cli_setup


def test_run_creates_dirs_and_writes_default_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    cli_setup.run(uninstall=False, purge_data=False)
    assert (tmp_path / "data" / "global").exists()
    assert (tmp_path / "cfg" / "config.yaml").exists()


def test_run_uninstall_removes_units_keeps_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "data").mkdir(parents=True)
    uninstalled = []
    fake_scheduler = MagicMock()
    fake_scheduler.uninstall.side_effect = lambda name: uninstalled.append(name)
    monkeypatch.setattr("claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler)
    cli_setup.run(uninstall=True, purge_data=False)
    assert (tmp_path / "data").exists()
    assert "com.claude-almanac.digest" in uninstalled


def test_run_purge_data_wipes_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "data" / "global").mkdir(parents=True)
    (tmp_path / "data" / "global" / "test.txt").write_text("keep me?")
    monkeypatch.setattr("claude_almanac.cli.setup.get_scheduler", lambda: MagicMock())
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    cli_setup.run(uninstall=True, purge_data=True)
    assert not (tmp_path / "data" / "global" / "test.txt").exists()
