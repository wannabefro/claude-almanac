import subprocess
import time
from pathlib import Path

import pytest

from claude_almanac.digest import collectors


def test_collect_new_memories_finds_fresh_files(tmp_path):
    g = tmp_path / "global"
    g.mkdir()
    f = g / "new_thing.md"
    f.write_text("---\ntype: project\nname: New Thing\ndescription: hello\n---\nbody\n")
    stale = g / "stale.md"
    stale.write_text("---\ntype: project\nname: Stale\n---\n")
    old = time.time() - 7 * 86400
    import os
    os.utime(stale, (old, old))
    p = tmp_path / "projects" / "git-abc"
    p.mkdir(parents=True)
    (p / "project_note.md").write_text("---\ntype: project\nname: Note\n---\n")

    out = collectors.collect_new_memories(
        global_dir=str(g), projects_dir=str(p.parent),
        cutoff_ts=time.time() - 3600,
    )
    names = sorted(m["slug"] for m in out)
    assert names == ["new_thing", "project_note"]
    scopes = {m["slug"]: m["scope"] for m in out}
    assert scopes["new_thing"] == "global"
    assert scopes["project_note"] == "git-abc"


def test_collect_new_memories_excludes_index(tmp_path):
    g = tmp_path / "global"
    g.mkdir()
    (g / "MEMORY.md").write_text("# index\n")
    (g / "real.md").write_text("---\ntype: project\n---\n")
    out = collectors.collect_new_memories(
        global_dir=str(g), projects_dir=str(tmp_path / "projects"),
        cutoff_ts=0.0,
    )
    assert len(out) == 1
    assert out[0]["slug"] == "real"


def test_collect_retrievals_missing_log_returns_empty(tmp_path):
    out = collectors.collect_retrievals(
        log_path=str(tmp_path / "absent.log"), cutoff_iso="2020-01-01T00:00:00Z",
    )
    assert out == {}


def test_collect_retrievals_tallies_sources(tmp_path):
    log = tmp_path / "retrieve.log"
    log.write_text(
        'ts=2026-04-19T10:00:00Z event=memory.injected sources=md:a.md,md:b.md\n'
        'ts=2026-04-19T10:05:00Z event=memory.injected sources=md:a.md\n'
        'ts=2020-01-01T00:00:00Z event=memory.injected sources=md:old.md\n'
    )
    out = collectors.collect_retrievals(
        log_path=str(log), cutoff_iso="2026-04-19T00:00:00Z",
    )
    assert out == {"md:a.md": 2, "md:b.md": 1}


def test_collect_git_activity_returns_commits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add a"], cwd=repo, check=True, capture_output=True)

    out = collectors.collect_git_activity(
        repo_path=str(repo), repo_name="repo", since_iso="1970-01-01T00:00:00Z",
    )
    assert len(out) == 1
    assert out[0].subject == "feat: add a"
    assert out[0].repo == "repo"
    assert out[0].stat_insertions >= 1


def test_collect_git_activity_non_repo_returns_empty(tmp_path):
    (tmp_path / "notarepo").mkdir()
    out = collectors.collect_git_activity(
        repo_path=str(tmp_path / "notarepo"),
        repo_name="x", since_iso="1970-01-01T00:00:00Z",
    )
    assert out == []
