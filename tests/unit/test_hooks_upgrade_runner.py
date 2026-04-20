"""Tests for the detached `uv tool upgrade` runner."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from claude_almanac.hooks import upgrade_runner


def test_runner_writes_status_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    fake_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(upgrade_runner.subprocess, "run", fake_run)
    exit_code = upgrade_runner._run("0.2.2")
    assert exit_code == 0
    status = json.loads((tmp_path / "logs" / "upgrade.status.json").read_text())
    assert status["exit"] == 0
    assert status["target"] == "0.2.2"
    assert isinstance(status["ts"], int)
    # Verify the FIRST subprocess call was uv upgrade against the public index
    # (the second call is `claude-almanac setup` — covered in its own test).
    upgrade_cmd = fake_run.call_args_list[0][0][0]
    assert "--default-index" in upgrade_cmd
    assert "https://pypi.org/simple/" in upgrade_cmd


def test_runner_writes_status_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    fake_run = MagicMock(return_value=MagicMock(returncode=2))
    monkeypatch.setattr(upgrade_runner.subprocess, "run", fake_run)
    exit_code = upgrade_runner._run("0.2.2")
    assert exit_code == 2
    status = json.loads((tmp_path / "logs" / "upgrade.status.json").read_text())
    assert status["exit"] == 2


def test_runner_invokes_setup_on_success(tmp_path, monkeypatch):
    """After a clean `uv tool upgrade`, the runner must call
    `claude-almanac setup` to re-register launchd/systemd units so long-lived
    daemons get relaunched under the new venv. Without this, users hit
    stale-process 500s until they restart units manually."""
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    calls: list[list[str]] = []

    def _fake_run(cmd, **kw):
        calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(upgrade_runner.subprocess, "run", _fake_run)
    assert upgrade_runner._run("0.2.6") == 0
    # uv upgrade, then claude-almanac setup — in that order.
    assert len(calls) == 2
    assert calls[0][:3] == ["uv", "tool", "upgrade"]
    assert calls[1] == ["claude-almanac", "setup"]


def test_runner_skips_setup_when_upgrade_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    calls: list[list[str]] = []

    def _fake_run(cmd, **kw):
        calls.append(cmd)
        return MagicMock(returncode=2)

    monkeypatch.setattr(upgrade_runner.subprocess, "run", _fake_run)
    assert upgrade_runner._run("0.2.6") == 2
    # Only the failed uv upgrade; no setup invocation because upgrade failed.
    assert len(calls) == 1
    assert calls[0][:3] == ["uv", "tool", "upgrade"]


def test_runner_records_launch_failure_as_127(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))

    def _raise(*a, **kw):
        raise FileNotFoundError("uv not found on PATH")

    monkeypatch.setattr(upgrade_runner.subprocess, "run", _raise)
    exit_code = upgrade_runner._run("0.2.2")
    assert exit_code == 127
    status = json.loads((tmp_path / "logs" / "upgrade.status.json").read_text())
    assert status["exit"] == 127
