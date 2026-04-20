"""End-to-end: codeindex init on a tiny fixture repo → recall code finds a symbol."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _init_fixture_repo(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "math_utils.py").write_text(
        "def compute_rolling_mean(values: list[float]) -> float:\n"
        "    return sum(values) / max(len(values), 1)\n"
    )
    (root / "pkg" / "strings.py").write_text(
        "def slugify(text: str) -> str:\n"
        "    return text.lower().replace(' ', '-')\n"
    )
    # codeindex init requires .claude/code-index.yaml
    (root / ".claude").mkdir()
    (root / ".claude" / "code-index.yaml").write_text(
        "default_branch: main\n"
        "modules:\n"
        "  patterns:\n"
        "    - pkg\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root, check=True,
    )


def test_codeindex_init_then_recall_code_finds_symbol(isolated_data_dir):
    repo = isolated_data_dir / "fixture-repo"
    repo.mkdir()
    _init_fixture_repo(repo)
    env = {
        **os.environ,
        "CLAUDE_ALMANAC_DATA_DIR": os.environ["CLAUDE_ALMANAC_DATA_DIR"],
    }
    init = subprocess.run(
        ["claude-almanac", "codeindex", "init", "--repo", str(repo)],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=120,
    )
    assert init.returncode == 0, init.stderr
    search = subprocess.run(
        ["claude-almanac", "recall", "code", "rolling mean"],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=30,
    )
    assert search.returncode == 0, search.stderr
    assert "compute_rolling_mean" in search.stdout
