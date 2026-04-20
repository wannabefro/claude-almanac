"""Isolate codeindex unit tests from the real XDG data dir.

Several functions under ``claude_almanac.codeindex`` (arch, sym, init, refresh)
open ``paths.logs_dir() / "code-index.log"`` unconditionally. Without a
per-test override of ``CLAUDE_ALMANAC_DATA_DIR`` the logger writes to the
user's real ~/Library/Application Support/claude-almanac/logs/ directory,
polluting the production log with synthetic test values (module=m,
err=boom, symbol=pub, sha=sha1, …) every time the unit suite runs.

This autouse fixture pins the data + config dirs to pytest's tmp_path for
every test in the codeindex subpackage.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_claude_almanac_paths(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("almanac")
    monkeypatch.setenv("CLAUDE_ALMANAC_DATA_DIR", str(d / "data"))
    monkeypatch.setenv("CLAUDE_ALMANAC_CONFIG_DIR", str(d / "cfg"))
