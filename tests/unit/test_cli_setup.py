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
    cfg.content_index.daily_refresh = True
    cfg.content_index.refresh_hour = 3
    cfg.digest.repos = [core_config.RepoCfg(path=str(tmp_path), alias="x")]
    monkeypatch.setattr("claude_almanac.cli.setup.core_config.load", lambda: cfg)
    from claude_almanac.cli import setup as cli_setup
    cli_setup.run(uninstall=False, purge_data=False)
    daily_calls = [
        c for c in fake_scheduler.method_calls if c[0] == "install_daily"
    ]
    codeindex_call = next(
        c for c in daily_calls
        if c.args[0] == "com.claude-almanac.contentindex-refresh"
    )
    assert codeindex_call.args[2] == 3
    # The command ends with the --all flag so the cron walks digest.repos.
    assert codeindex_call.args[1][-3:] == ["content", "refresh", "--all"]


def test_install_cleans_up_legacy_codeindex_unit(tmp_path, monkeypatch):
    """Upgrading from v0.3.x must remove the orphan launchd/systemd unit that
    pointed at the (now-invalid) `codeindex refresh --all` command. Task 7
    renamed the unit to com.claude-almanac.contentindex-refresh; the legacy
    uninstall runs on every `_do_install` via `_reinstall_units_under_new_names`.
    """
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr("claude_almanac.cli.setup._probe_embedder", lambda: True)
    fake_scheduler = MagicMock()
    monkeypatch.setattr(
        "claude_almanac.cli.setup.get_scheduler", lambda: fake_scheduler,
    )
    cli_setup.run(uninstall=False, purge_data=False)
    uninstall_calls = [
        c.args[0] if c.args else c.kwargs.get("unit_name")
        for c in fake_scheduler.uninstall.call_args_list
    ]
    assert "com.claude-almanac.codeindex-refresh" in uninstall_calls, (
        f"expected legacy unit cleanup, got uninstall calls: {uninstall_calls}"
    )


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
        c.args[0] == "com.claude-almanac.contentindex-refresh"
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
    assert "com.claude-almanac.contentindex-refresh" in uninstalled


def test_setup_migration_sets_anthropic_when_api_key_present(tmp_path, monkeypatch, capsys):
    """Fresh install + API key in env -> anthropic_sdk provider written."""
    from claude_almanac.cli import setup as setup_mod

    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")

    setup_mod._migrate_curator_provider()

    import yaml
    raw = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert raw["curator"]["provider"] == "anthropic_sdk"
    assert raw["curator"]["model"] == "claude-haiku-4-5-20251001"
    out = capsys.readouterr().out
    assert "anthropic_sdk" in out


def test_setup_migration_sets_ollama_when_no_api_key(tmp_path, monkeypatch, capsys):
    from claude_almanac.cli import setup as setup_mod

    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    pulled = []
    monkeypatch.setattr(setup_mod, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(setup_mod, "_ollama_pull", lambda model: pulled.append(model))

    setup_mod._migrate_curator_provider()

    import yaml
    raw = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert raw["curator"]["provider"] == "ollama"
    assert raw["curator"]["model"] == "gemma3:4b"
    assert pulled == ["gemma3:4b"]
    out = capsys.readouterr().out
    assert "ollama" in out
    assert "gemma3:4b" in out


def test_setup_migration_warns_when_ollama_unreachable(tmp_path, monkeypatch, capsys):
    from claude_almanac.cli import setup as setup_mod

    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(setup_mod, "_ollama_reachable", lambda: False)

    called = []
    monkeypatch.setattr(setup_mod, "_ollama_pull", lambda m: called.append(m))

    setup_mod._migrate_curator_provider()

    import yaml
    raw = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert raw["curator"]["provider"] == "ollama"   # still written
    assert called == []                              # pull skipped
    out = capsys.readouterr().out
    assert "warn" in out.lower() or "unreachable" in out.lower()


def test_setup_migration_is_idempotent_when_curator_block_exists(
    tmp_path, monkeypatch, capsys,
):
    """User already configured anthropic_sdk. No API key in env. Must not
    silently downgrade to ollama."""
    from claude_almanac.cli import setup as setup_mod

    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "config.yaml").write_text(
        "curator:\n"
        "  provider: anthropic_sdk\n"
        "  model: claude-haiku-4-5-20251001\n"
        "  timeout_s: 15\n"
    )

    setup_mod._migrate_curator_provider()

    import yaml
    raw = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert raw["curator"]["provider"] == "anthropic_sdk"


def test_setup_migration_reheals_ollama_pull_when_already_configured(
    tmp_path, monkeypatch,
):
    """If the user already has curator.provider=ollama, re-running setup
    pulls the model again (idempotent; cheap no-op if present)."""
    from claude_almanac.cli import setup as setup_mod

    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "curator:\n  provider: ollama\n  model: gemma3:4b\n  timeout_s: 0\n"
    )
    pulls = []
    monkeypatch.setattr(setup_mod, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(setup_mod, "_ollama_pull", lambda m: pulls.append(m))

    setup_mod._migrate_curator_provider()

    assert pulls == ["gemma3:4b"]
