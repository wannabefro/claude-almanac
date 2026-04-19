"""git_show — fetch a commit's subject + diff from a configured repo."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from claude_almanac.core import config as core_config
from claude_almanac.digest.qa.registry import tool

_SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")


def _resolve_repo_path(name: str) -> str | None:
    cfg = core_config.load()
    for r in cfg.digest.repos:
        if r.alias == name:
            return str(Path(r.path).expanduser())
    return None


@tool(
    "git_show",
    "Fetch the subject and diff for a commit SHA in a configured repo. "
    "Use when you need the actual code change, not a summary.",
)
def git_show(
    repo: str,
    sha: str,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    if not _SHA_RE.match(sha):
        return {"error": f"invalid sha format: {sha!r}"}
    path = _resolve_repo_path(repo)
    if not path:
        return {"error": f"unknown repo: {repo}"}
    if not Path(path).is_dir():
        return {"error": f"repo path missing: {path}"}

    try:
        subj = subprocess.run(
            ["git", "log", "-1", "--format=%s%n%b", sha, "--"],
            cwd=path, capture_output=True, text=True, timeout=5, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "git log timeout"}
    if subj.returncode != 0:
        return {"error": f"unknown sha: {sha}"}
    subject = subj.stdout.strip().split("\n", 1)[0]

    try:
        diff = subprocess.run(
            ["git", "show", "--format=", "--no-color", sha, "--"],
            cwd=path, capture_output=True, text=True, timeout=10, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"error": "git show timeout"}
    if diff.returncode != 0:
        return {"error": "git show failed"}

    full = diff.stdout
    encoded = full.encode("utf-8")
    if len(encoded) > max_bytes:
        truncated = (
            encoded[:max_bytes].decode("utf-8", errors="replace")
            + "\n...(truncated)"
        )
    else:
        truncated = full
    return {"repo": repo, "sha": sha, "subject": subject, "diff": truncated}
