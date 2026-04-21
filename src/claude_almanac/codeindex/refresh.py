"""Incremental refresh: fetch origin, diff against last_sha, re-embed changed files."""
from __future__ import annotations

import os
import pathlib
import subprocess
import time

os.environ.pop("DEVELOPER_DIR", None)

from claude_almanac.codeindex import config as _cfg
from claude_almanac.codeindex import db as _db
from claude_almanac.codeindex import sym as _sym
from claude_almanac.codeindex.log import emit
from claude_almanac.core import config as _app_config
from claude_almanac.core import paths
from claude_almanac.embedders import make_embedder as _make_embedder


def resolve_module_for_file(rel_path: str, modules: list[_cfg.Module]) -> str | None:
    """Longest-prefix match of a repo-relative file path against module names."""
    best: _cfg.Module | None = None
    for m in modules:
        prefix = m.name.rstrip("/") + "/"
        if (rel_path == m.name or rel_path.startswith(prefix)) and (
            best is None or len(m.name) > len(best.name)
        ):
            best = m
    return best.name if best else None


def _git(args: list[str], cwd: str) -> str:
    return subprocess.check_output(["git"] + args, cwd=cwd, text=True).strip()


def _ci_db_path() -> pathlib.Path:
    p = paths.project_memory_dir() / "code-index.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def main(repo_root: str) -> int:
    log_path = paths.logs_dir() / "code-index.log"
    repo_root = str(pathlib.Path(repo_root).resolve())
    c = _cfg.load(repo_root)
    mods = _cfg.discover_modules(c)
    dbp = _ci_db_path()
    if not dbp.exists():
        emit(log_path, component="code-index", level="warn",
             event="refresh.no_db", repo=repo_root)
        print("no code-index.db — run `claude-almanac codeindex init` first")
        return 1
    app_cfg = _app_config.load()
    embedder = _make_embedder(app_cfg.embedder.provider, app_cfg.embedder.model)
    last = _db.last_sha(str(dbp))
    try:
        _git(["fetch", "origin", c.default_branch], repo_root)
        target = _git(["rev-parse", f"origin/{c.default_branch}"], repo_root)
    except subprocess.CalledProcessError:
        emit(log_path, component="code-index", level="warn",
             event="refresh.no_origin", repo=repo_root, branch=c.default_branch)
        target = _git(["rev-parse", "HEAD"], repo_root)
    if last == target:
        emit(log_path, component="code-index", level="info",
             event="refresh.clean", repo=repo_root, sha=target)
        print("clean — nothing to do")
        return 0
    if last:
        try:
            changed = _git(
                ["diff", "--name-only", f"{last}..{target}"], repo_root,
            ).splitlines()
        except subprocess.CalledProcessError:
            # last_sha points at a commit that no longer exists (force-push,
            # rewritten history, or a stale placeholder from an earlier buggy
            # init). Treat as "no common ancestor" → re-index everything.
            emit(log_path, component="code-index", level="warn",
                 event="refresh.stale_last_sha", repo=repo_root,
                 last=last, target=target)
            changed = []
    else:
        changed = []
    t0 = time.time()
    files_processed = 0
    modules_dirty: set[str] = set()
    for rel in changed:
        mod_name = resolve_module_for_file(rel, mods)
        if mod_name is None:
            continue
        _db.delete_by_file(str(dbp), rel)
        abs_path = pathlib.Path(repo_root) / rel
        mod = next(m for m in mods if m.name == mod_name)
        mod_files = _cfg.enumerate_files(mod, c.extra_excludes)
        mix = _cfg.detect_language_mix(mod_files)
        if abs_path.exists() and _cfg.is_sym_capable(mix) and str(abs_path) in mod_files:
            try:
                _sym.extract_file(
                    db_path=str(dbp), repo_root=repo_root, module=mod_name,
                    file_abs=str(abs_path), commit_sha=target, embedder=embedder,
                )
            except Exception as e:
                emit(log_path, component="code-index", level="error",
                     event="refresh.file_fail", module=mod_name, file=rel, err=str(e))
        _db.mark_dirty(str(dbp), module=mod_name, sha=target)
        modules_dirty.add(mod_name)
        files_processed += 1
    emit(log_path, component="code-index", level="info", event="refresh.done",
         repo=repo_root, files=files_processed, modules_dirty=len(modules_dirty),
         sha=target, dur_ms=int((time.time() - t0) * 1000))
    print(f"refresh done: {files_processed} files, {len(modules_dirty)} modules dirty")
    return 0
