"""Regression tests for project_key's cwd robustness.

Background-fired curator and rollup runners inherit cwd from whatever
process forked them. If that directory is deleted before the background
process runs, Path.cwd() raises FileNotFoundError and takes down the
whole curator pass. project_key must degrade gracefully to a stable
sentinel key rather than bubble the error.
"""
from __future__ import annotations

from unittest.mock import patch

from claude_almanac.core import paths


def test_project_key_returns_sentinel_when_cwd_missing(monkeypatch):
    # Simulate a deleted/unreachable cwd.
    def _raise(*args, **kwargs):
        raise FileNotFoundError(2, "No such file", ".")
    monkeypatch.setattr(paths, "_safe_cwd", lambda: None)
    assert paths.project_key() == "cwd-unknown"


def test_project_key_returns_git_key_when_cwd_valid_and_in_repo(tmp_path, monkeypatch):
    # Seed a .git directory so the walk-up fallback resolves to a git key.
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(paths, "_safe_cwd", lambda: tmp_path)
    # Force git CLI branch to fail so fallback kicks in.
    def _fake_run(*args, **kwargs):
        import subprocess
        raise subprocess.CalledProcessError(returncode=128, cmd=args[0])
    with patch("claude_almanac.core.paths.subprocess.run", _fake_run):
        key = paths.project_key()
    assert key.startswith("git-")


def test_project_memory_dir_composes_sentinel(monkeypatch):
    """When project_key is the unknown sentinel, project_memory_dir still
    yields a usable path — the curator can write to cwd-unknown without
    crashing."""
    monkeypatch.setattr(paths, "_safe_cwd", lambda: None)
    p = paths.project_memory_dir()
    assert p.name == "cwd-unknown"
