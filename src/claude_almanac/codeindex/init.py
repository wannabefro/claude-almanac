"""First-time code-index build for the current repo.

Writes <project_data_dir>/code-index.db + a `repo_root` sidecar so the
refresh command can locate the repo from the DB alone.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import time

# Apple /usr/bin/git is a stub; direnv setups can set DEVELOPER_DIR to a non-Xcode
# SDK which makes the stub error. Unset for our subprocesses.
os.environ.pop("DEVELOPER_DIR", None)

from claude_almanac.codeindex import config as _cfg
from claude_almanac.codeindex import sym as _sym
from claude_almanac.codeindex.log import emit
from claude_almanac.contentindex import db as _db
from claude_almanac.core import config as _app_config
from claude_almanac.core import paths
from claude_almanac.embedders import make_embedder as _make_embedder


def _ci_db_path() -> pathlib.Path:
    p = paths.project_memory_dir() / "code-index.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _target_sha(repo_root: str, default_branch: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", f"origin/{default_branch}"],
            cwd=repo_root, text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True,
        ).strip()


def main(repo_root: str) -> int:
    log_path = paths.logs_dir() / "code-index.log"
    repo_root = str(pathlib.Path(repo_root).resolve())
    c = _cfg.load(repo_root)
    mods = _cfg.discover_modules(c)
    dbp = _ci_db_path()
    app_cfg = _app_config.load()
    embedder = _make_embedder(app_cfg.embedder.provider, app_cfg.embedder.model)
    _db.init(str(dbp), dim=embedder.dim)
    (dbp.parent / "repo_root").write_text(repo_root)
    target_sha = _target_sha(repo_root, c.default_branch)

    total = 0
    for m in mods:
        files_ = _cfg.enumerate_files(m, c.extra_excludes)
        mix = _cfg.detect_language_mix(files_)
        if not _cfg.is_sym_capable(mix):
            emit(log_path, component="code-index", level="info",
                 event="init.skip_sym", module=m.name, reason="not_sym_capable",
                 mix=str(mix))
            _db.mark_dirty(str(dbp), module=m.name, sha=target_sha)
            continue
        t0 = time.time()
        written = 0
        for f in files_:
            try:
                written += _sym.extract_file(
                    db_path=str(dbp), repo_root=repo_root, module=m.name,
                    file_abs=f, commit_sha=target_sha, embedder=embedder,
                )
            except Exception as e:
                emit(log_path, component="code-index", level="error",
                     event="init.file_fail", module=m.name,
                     file=str(pathlib.Path(f).relative_to(repo_root)), err=str(e))
        emit(log_path, component="code-index", level="info",
             event="init.module_done", module=m.name, files=len(files_),
             sym_written=written, dur_ms=int((time.time() - t0) * 1000))
        _db.mark_dirty(str(dbp), module=m.name, sha=target_sha)
        total += written
    emit(log_path, component="code-index", level="info", event="init.done",
         repo=repo_root, modules=len(mods), sym_written=total, sha=target_sha)
    print(f"init complete: {len(mods)} modules, {total} sym entries, dirty={len(mods)}")
    return 0
