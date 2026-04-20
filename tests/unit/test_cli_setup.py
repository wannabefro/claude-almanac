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


def test_install_daily_registers_generator_and_server(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    from unittest.mock import MagicMock
    fake_scheduler = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    # Enable digest in default config before save
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.digest.enabled = True
    cfg.digest.repos = [core_config.RepoCfg(path=str(tmp_path), alias="ok")]
    cfg.digest.hour = 9
    monkeypatch.setattr(
        "claude_almanac.cli.setup.core_config.load", lambda: cfg,
    )
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=False, purge_data=False)
    method_names = [c[0] for c in fake_scheduler.method_calls]
    assert "install_daily" in method_names
    assert "install_always_on" in method_names
    daily_call = next(c for c in fake_scheduler.method_calls if c[0] == "install_daily")
    assert daily_call.args[0] == "com.claude-almanac.digest"
    assert daily_call.args[2] == 9
    always_call = next(
        c for c in fake_scheduler.method_calls if c[0] == "install_always_on"
    )
    assert always_call.args[0] == "com.claude-almanac.server"


def test_install_skips_units_when_digest_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    from unittest.mock import MagicMock
    fake_scheduler = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=False, purge_data=False)
    method_names = [c[0] for c in fake_scheduler.method_calls]
    assert "install_daily" not in method_names
    assert "install_always_on" not in method_names


def test_install_registers_codeindex_refresh_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    from unittest.mock import MagicMock
    fake_scheduler = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    from claude_almanac.core import config as core_config
    cfg = core_config.default_config()
    cfg.code_index.daily_refresh = True
    cfg.code_index.refresh_hour = 3
    cfg.digest.repos = [core_config.RepoCfg(path=str(tmp_path), alias="x")]
    monkeypatch.setattr("claude_almanac.cli.setup.core_config.load", lambda: cfg)
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=False, purge_data=False)
    daily_calls = [
        c for c in fake_scheduler.method_calls if c[0] == "install_daily"
    ]
    codeindex_call = next(
        c for c in daily_calls
        if c.args[0] == "com.claude-almanac.codeindex-refresh"
    )
    assert codeindex_call.args[2] == 3
    # The command ends with the --all flag so the cron walks code_index.repos.
    assert codeindex_call.args[1][-3:] == ["codeindex", "refresh", "--all"]


def test_install_uninstalls_codeindex_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    from unittest.mock import MagicMock
    fake_scheduler = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    # daily_refresh=False (default) should trigger a best-effort uninstall so
    # flipping the flag off cleanly removes the scheduled job.
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=False, purge_data=False)
    uninstall_calls = [
        c for c in fake_scheduler.method_calls if c[0] == "uninstall"
    ]
    assert any(
        c.args[0] == "com.claude-almanac.codeindex-refresh"
        for c in uninstall_calls
    )


def test_uninstall_removes_codeindex_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "data").mkdir(parents=True)
    uninstalled = []
    fake_scheduler = MagicMock()
    fake_scheduler.uninstall.side_effect = lambda name: uninstalled.append(name)
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=True, purge_data=False)
    assert "com.claude-almanac.codeindex-refresh" in uninstalled
