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
    # Verify the subprocess was invoked against the public index.
    cmd = fake_run.call_args[0][0]
    assert "--default-index" in cmd
    assert "https://pypi.org/simple/" in cmd


def test_runner_writes_status_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))
    fake_run = MagicMock(return_value=MagicMock(returncode=2))
    monkeypatch.setattr(upgrade_runner.subprocess, "run", fake_run)
    exit_code = upgrade_runner._run("0.2.2")
    assert exit_code == 2
    status = json.loads((tmp_path / "logs" / "upgrade.status.json").read_text())
    assert status["exit"] == 2


def test_runner_records_launch_failure_as_127(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(tmp_path))

    def _raise(*a, **kw):
        raise FileNotFoundError("uv not found on PATH")

    monkeypatch.setattr(upgrade_runner.subprocess, "run", _raise)
    exit_code = upgrade_runner._run("0.2.2")
    assert exit_code == 127
    status = json.loads((tmp_path / "logs" / "upgrade.status.json").read_text())
    assert status["exit"] == 127
