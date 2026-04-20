"""Tests for the SessionStart upgrade-drift hook."""
from __future__ import annotations

import json
from unittest.mock import patch

from claude_almanac.hooks import upgrade as _upgrade


def _write_plugin_json(tmp_path, version: str) -> str:
    (tmp_path / "plugin.json").write_text(json.dumps({"version": version}))
    return str(tmp_path)


def test_returns_silently_when_plugin_root_missing(monkeypatch, capsys):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _upgrade.main()
    assert capsys.readouterr().out == ""


def test_returns_silently_when_versions_match(tmp_path, monkeypatch, capsys):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    with patch.object(_upgrade, "_installed_version", return_value="0.1.2"):
        _upgrade.main()
    assert capsys.readouterr().out == ""


def test_prints_notice_when_drift_and_auto_upgrade_off(tmp_path, monkeypatch, capsys):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    with patch.object(_upgrade, "_installed_version", return_value="0.1.1"):
        _upgrade.main()
    out = capsys.readouterr().out
    assert "plugin v0.1.2" in out
    assert "CLI v0.1.1" in out
    assert "uv tool upgrade claude-almanac" in out


def test_launches_upgrade_when_auto_upgrade_on_and_uv(tmp_path, monkeypatch, capsys):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    c = core_config.default_config()
    c.auto_upgrade = True
    core_config.save(c)

    popen_calls: list[list[str]] = []

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            popen_calls.append(cmd)

    with patch.object(_upgrade, "_installed_version", return_value="0.1.1"), \
         patch.object(_upgrade, "_detect_uv_install", return_value=True), \
         patch.object(_upgrade.subprocess, "Popen", _FakePopen):
        _upgrade.main()

    # Spawn goes through the detached runner module, not uv directly.
    assert len(popen_calls) == 1
    cmd = popen_calls[0]
    assert cmd[1:] == ["-m", "claude_almanac.hooks.upgrade_runner", "0.1.2"]
    out = capsys.readouterr().out
    assert "upgrading CLI v0.1.1 -> v0.1.2" in out


def test_short_circuits_when_last_attempt_for_this_target_failed(
    tmp_path, monkeypatch, capsys
):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    from claude_almanac.core import paths
    c = core_config.default_config()
    c.auto_upgrade = True
    core_config.save(c)

    # Seed a failed status for the current plugin version.
    status_path = paths.logs_dir() / "upgrade.status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    import time
    status_path.write_text(json.dumps({
        "ts": int(time.time()) - 3600,  # 1h ago
        "exit": 2,
        "target": "0.1.2",
    }))

    popen_calls: list[list[str]] = []

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            popen_calls.append(cmd)

    with patch.object(_upgrade, "_installed_version", return_value="0.1.1"), \
         patch.object(_upgrade, "_detect_uv_install", return_value=True), \
         patch.object(_upgrade.subprocess, "Popen", _FakePopen):
        _upgrade.main()

    assert popen_calls == []  # no retry
    out = capsys.readouterr().out
    assert "last auto-upgrade to v0.1.2 failed" in out
    assert "exit=2" in out


def test_retries_when_prior_failure_targeted_a_different_version(
    tmp_path, monkeypatch, capsys
):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    from claude_almanac.core import paths
    c = core_config.default_config()
    c.auto_upgrade = True
    core_config.save(c)

    # Prior failure targeted an older version — newer plugin should retry.
    status_path = paths.logs_dir() / "upgrade.status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({
        "ts": 1700000000,
        "exit": 1,
        "target": "0.1.1",
    }))

    popen_calls: list[list[str]] = []

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            popen_calls.append(cmd)

    with patch.object(_upgrade, "_installed_version", return_value="0.1.1"), \
         patch.object(_upgrade, "_detect_uv_install", return_value=True), \
         patch.object(_upgrade.subprocess, "Popen", _FakePopen):
        _upgrade.main()

    assert len(popen_calls) == 1  # retry happened


def test_skips_auto_upgrade_for_non_uv_install(tmp_path, monkeypatch, capsys):
    plugin_root = _write_plugin_json(tmp_path, "0.1.2")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(tmp_path / "cfg"))
    from claude_almanac.core import config as core_config
    c = core_config.default_config()
    c.auto_upgrade = True
    core_config.save(c)

    with patch.object(_upgrade, "_installed_version", return_value="0.1.1"), \
         patch.object(_upgrade, "_detect_uv_install", return_value=False):
        _upgrade.main()
    out = capsys.readouterr().out
    assert "auto_upgrade only supports uv" in out
