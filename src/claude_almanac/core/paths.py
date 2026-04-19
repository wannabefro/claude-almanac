"""XDG-compliant path resolution for claude-almanac data and config."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import platformdirs

APP_NAME = "claude-almanac"


def data_dir() -> Path:
    """Base data dir. macOS: ~/Library/Application Support/claude-almanac.
    Linux: $XDG_DATA_HOME/claude-almanac (fallback ~/.local/share/claude-almanac).
    Overridable via CLAUDE_ALMANAC_DATA_DIR."""
    override = os.environ.get("CLAUDE_ALMANAC_DATA_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_data_dir(APP_NAME))


def config_dir() -> Path:
    """Base config dir. Unified on ~/.config/claude-almanac for both macOS and Linux.
    We deliberately diverge from `platformdirs.user_config_dir` on macOS (which returns
    ~/Library/Application Support) so contributors and users can find/edit config.yaml
    in the familiar ~/.config location. Overridable via CLAUDE_ALMANAC_CONFIG_DIR."""
    override = os.environ.get("CLAUDE_ALMANAC_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / APP_NAME


def global_memory_dir() -> Path:
    return data_dir() / "global"


def projects_memory_dir() -> Path:
    return data_dir() / "projects"


def digests_dir() -> Path:
    return data_dir() / "digests"


def logs_dir() -> Path:
    return data_dir() / "logs"


def project_key() -> str:
    """Stable per-repo key. Uses git-common-dir parent so worktrees share storage.
    Falls back to cwd-<hash> when not inside a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_common = Path(result.stdout.strip())
        if not git_common.is_absolute():
            git_common = (Path.cwd() / git_common).resolve()
        else:
            git_common = git_common.resolve()
        # Parent of .git is the repo root; for worktrees this points at the primary repo.
        root = git_common.parent if git_common.name == ".git" else git_common
        digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
        return f"git-{digest}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: walk up from cwd looking for a .git directory or file.
        # This handles cases where the git CLI is unavailable or the repo
        # is only partially initialized (e.g. empty .git/ in tests).
        cwd = Path.cwd().resolve()
        for candidate in (cwd, *cwd.parents):
            if (candidate / ".git").exists():
                digest = hashlib.sha256(str(candidate).encode()).hexdigest()[:16]
                return f"git-{digest}"
        cwd_digest = hashlib.sha256(str(cwd).encode()).hexdigest()[:16]
        return f"cwd-{cwd_digest}"


def project_memory_dir() -> Path:
    return projects_memory_dir() / project_key()


def ensure_dirs() -> None:
    """Create all standard dirs if absent. Safe to call repeatedly."""
    for d in (global_memory_dir(), projects_memory_dir(), digests_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
