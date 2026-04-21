"""Unit tests for subprocess-based curator providers (claude_cli + codex).

Tests mock ``subprocess.run`` to avoid requiring the real CLIs on CI.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from claude_almanac.curators.claude_cli import ClaudeCliCurator
from claude_almanac.curators.codex import CodexCurator


def _make_completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# --- ClaudeCliCurator ---

def test_claude_cli_invokes_subprocess_with_expected_args():
    c = ClaudeCliCurator(model="claude-haiku-4-5", timeout_s=60.0)
    with patch("subprocess.run") as run:
        run.return_value = _make_completed(stdout='{"decisions": []}')
        out = c.invoke("SYS", "USER")
    assert out == '{"decisions": []}'
    args = run.call_args.args[0]
    assert args[0] == "claude"
    assert "-p" in args
    assert "--model" in args
    assert "claude-haiku-4-5" in args
    assert any("SYS" in a and "USER" in a for a in args)


def test_claude_cli_empty_user_turn_uses_only_system_prompt():
    c = ClaudeCliCurator(model="claude-haiku-4-5", timeout_s=60.0)
    with patch("subprocess.run") as run:
        run.return_value = _make_completed(stdout="ok")
        c.invoke("SYS ONLY", "")
    prompt = run.call_args.args[0][-1]
    assert prompt == "SYS ONLY"


def test_claude_cli_timeout_returns_empty_string():
    c = ClaudeCliCurator(timeout_s=1.0)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
        out = c.invoke("x", "y")
    assert out == ""


def test_claude_cli_missing_binary_returns_empty():
    c = ClaudeCliCurator(binary="/nonexistent/claude")
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        out = c.invoke("x", "y")
    assert out == ""


def test_claude_cli_nonzero_returncode_returns_empty():
    c = ClaudeCliCurator()
    with patch("subprocess.run") as run:
        run.return_value = _make_completed(returncode=1, stderr="auth failed")
        out = c.invoke("x", "y")
    assert out == ""


# --- CodexCurator ---

def test_codex_invokes_subprocess_with_exec_and_sandbox_flags():
    c = CodexCurator(model="gpt-5-4", timeout_s=60.0)
    with patch("subprocess.run") as run:
        run.return_value = _make_completed(stdout='{"decisions": []}')
        out = c.invoke("SYS", "USER")
    assert out == '{"decisions": []}'
    args = run.call_args.args[0]
    assert args[0] == "codex"
    assert args[1] == "exec"
    assert "--skip-git-repo-check" in args
    assert "--ephemeral" in args
    assert "-s" in args
    assert "read-only" in args
    assert "-m" in args
    assert "gpt-5-4" in args


def test_codex_omits_model_flag_when_blank():
    c = CodexCurator(model="", timeout_s=60.0)
    with patch("subprocess.run") as run:
        run.return_value = _make_completed(stdout="ok")
        c.invoke("SYS", "")
    args = run.call_args.args[0]
    assert "-m" not in args


def test_codex_timeout_returns_empty():
    c = CodexCurator(timeout_s=1.0)
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=1)):
        out = c.invoke("x", "y")
    assert out == ""


def test_codex_missing_binary_returns_empty():
    c = CodexCurator(binary="/nonexistent/codex")
    with patch("subprocess.run", side_effect=FileNotFoundError()):
        out = c.invoke("x", "y")
    assert out == ""


# --- Factory dispatch ---

def test_factory_dispatches_claude_cli():
    import dataclasses

    from claude_almanac.core.config import default_config
    from claude_almanac.curators.factory import make_curator

    cfg = default_config()
    cfg = dataclasses.replace(
        cfg, curator=dataclasses.replace(
            cfg.curator, provider="claude_cli", model="claude-haiku-4-5",
        ),
    )
    curator = make_curator(cfg)
    assert curator.name == "claude_cli"
    assert curator.model == "claude-haiku-4-5"


def test_factory_dispatches_codex():
    import dataclasses

    from claude_almanac.core.config import default_config
    from claude_almanac.curators.factory import make_curator

    cfg = default_config()
    cfg = dataclasses.replace(
        cfg, curator=dataclasses.replace(
            cfg.curator, provider="codex", model="gpt-5-4",
        ),
    )
    curator = make_curator(cfg)
    assert curator.name == "codex"
    assert curator.model == "gpt-5-4"
