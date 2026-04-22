"""Dispatch `claude-almanac content <init|refresh|arch|status>`."""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys


def _repo_or_cwd(args: argparse.Namespace) -> str:
    return args.repo if args.repo else os.getcwd()


def _resolve_commit_sha(repo: str) -> str:
    """Best-effort `git rev-parse HEAD` with a safe fallback. Mirrors the
    resolution used by `codeindex/init.py::_target_sha`'s fallback branch;
    doc ingest doesn't need the origin/<branch> tip, just something
    stable-ish for the commit_sha column."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def _run_doc_ingest(repo: str, *, verb: str) -> None:
    """Run documents.ingest (verb='init') or documents.refresh (verb='refresh')
    for a repo. Gated on the repo-local `.claude/code-index.yaml` `docs.enabled`
    flag (default True via DocsCfg). All failures are logged + printed as a
    single-line warning and do NOT fail the outer CLI command — the sym pass
    has already succeeded by the time we get here, and a broken documents
    subsystem shouldn't poison init/refresh.

    Imports are lazy so a breakage in `documents/` cannot prevent sym init
    from running when this helper is evaluated.
    """
    # Lazy imports — keep the sym path unaffected by documents/ breakage.
    try:
        from claude_almanac.codeindex import config as _ci_cfg
        from claude_almanac.codeindex.log import emit
        from claude_almanac.core import paths
        from claude_almanac.embedders import make_embedder as _make_embedder
    except Exception as e:
        print(f"doc {verb}: import failed ({e}); skipping", file=sys.stderr)
        return

    log_path = paths.logs_dir() / "content-index.log"

    try:
        c = _ci_cfg.load(repo)
    except Exception as e:
        emit(log_path, component="documents", level="warn",
             event=f"doc.{verb}.cfg_load_fail", repo=repo, err=str(e))
        print(f"doc {verb}: cfg load failed ({e}); skipping", file=sys.stderr)
        return

    if not c.docs.enabled:
        emit(log_path, component="documents", level="info",
             event=f"doc.{verb}.skip_disabled", repo=repo)
        return

    # Lazy import of app-level config + documents so any import error in
    # the documents package only affects the doc path, not sym.
    try:
        from claude_almanac.core import config as _app_config
        from claude_almanac.documents import ingest as _doc_ingest
        from claude_almanac.documents import refresh as _doc_refresh
    except Exception as e:
        emit(log_path, component="documents", level="error",
             event=f"doc.{verb}.import_fail", repo=repo, err=str(e))
        print(f"doc {verb}: import failed ({e}); skipping", file=sys.stderr)
        return

    db_path = str(paths.project_memory_dir() / "content-index.db")
    try:
        app_cfg = _app_config.load()
        embedder = _make_embedder(
            app_cfg.embedder.provider, app_cfg.embedder.model,
        )
    except Exception as e:
        emit(log_path, component="documents", level="error",
             event=f"doc.{verb}.embedder_fail", repo=repo, err=str(e))
        print(f"doc {verb}: embedder init failed ({e}); skipping",
              file=sys.stderr)
        return

    commit_sha = _resolve_commit_sha(repo)
    patterns = list(c.docs.patterns)
    excludes = list(c.docs.extra_excludes)
    try:
        if verb == "init":
            n = _doc_ingest.index_repo(
                repo_root=repo,
                db_path=db_path,
                embedder=embedder,
                patterns=patterns,
                excludes=excludes,
                chunk_max_chars=c.docs.chunk_max_chars,
                chunk_overlap_chars=c.docs.chunk_overlap_chars,
                commit_sha=commit_sha,
            )
            emit(log_path, component="documents", level="info",
                 event="doc.init.done", repo=repo, chunks=n)
            print(f"doc ingest: {n} chunks")
        elif verb == "refresh":
            n = _doc_refresh.refresh_repo(
                repo_root=repo,
                db_path=db_path,
                embedder=embedder,
                patterns=patterns,
                excludes=excludes,
                chunk_max_chars=c.docs.chunk_max_chars,
                chunk_overlap_chars=c.docs.chunk_overlap_chars,
                commit_sha=commit_sha,
            )
            emit(log_path, component="documents", level="info",
                 event="doc.refresh.done", repo=repo, chunks=n)
            print(f"doc refresh: {n} changed")
        else:
            raise ValueError(f"unknown verb: {verb}")
    except Exception as e:
        emit(log_path, component="documents", level="error",
             event=f"doc.{verb}.run_fail", repo=repo, err=str(e))
        print(f"doc {verb}: run failed ({e}); continuing", file=sys.stderr)


def cmd_init(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import init as _init
    repo = _repo_or_cwd(args)
    rc = _init.main(repo)
    if rc:
        return rc
    # v0.4.1 hotfix: after sym init succeeds, run doc ingest so
    # `recall docs` has content to search. Gated on repo-local
    # `.claude/code-index.yaml` docs.enabled (default True).
    _run_doc_ingest(repo, verb="init")
    return 0


def _refresh_one(repo_path: str) -> int:
    """Refresh a single repo. Run init first when the DB is missing so a
    brand-new entry in digest.repos doesn't require a manual bootstrap.
    Path resolution uses cwd (see paths.project_key), so we chdir in."""
    from claude_almanac.codeindex import init as _init
    from claude_almanac.codeindex import refresh as _refresh
    from claude_almanac.core import paths

    repo_path = str(pathlib.Path(repo_path).expanduser().resolve())
    prev_cwd = os.getcwd()
    try:
        os.chdir(repo_path)
        db_path = paths.project_memory_dir() / "content-index.db"
        if not db_path.exists():
            print(f"[{repo_path}] no content-index.db — running init")
            rc = _init.main(repo_path)
            if rc:
                return rc
            # Init bootstrapped the DB; also run doc ingest so the newly
            # created DB picks up docs rows in the same pass.
            _run_doc_ingest(repo_path, verb="init")
        rc = _refresh.main(repo_path)
        if rc:
            return rc
        # Doc refresh after sym refresh. Runs unconditionally for configured
        # repos; gated internally on repo-local docs.enabled.
        _run_doc_ingest(repo_path, verb="refresh")
        return 0
    finally:
        os.chdir(prev_cwd)


def cmd_refresh(args: argparse.Namespace) -> int:
    if getattr(args, "all_repos", False):
        from claude_almanac.core import config as _app_config
        cfg = _app_config.load()
        repos = cfg.digest.repos
        if not repos:
            print("no repos configured (set digest.repos in config.yaml)",
                  file=sys.stderr)
            return 1
        failures = 0
        for r in repos:
            print(f"=== refreshing {r.alias} ({r.path}) ===")
            try:
                rc = _refresh_one(r.path)
            except Exception as e:
                print(f"[{r.alias}] failed: {e}", file=sys.stderr)
                failures += 1
                continue
            if rc:
                print(f"[{r.alias}] returned non-zero ({rc})", file=sys.stderr)
                failures += 1
        return 1 if failures else 0
    from claude_almanac.codeindex import refresh as _refresh
    repo = _repo_or_cwd(args)
    rc = _refresh.main(repo)
    if rc:
        return rc
    # v0.4.1 hotfix: after sym refresh, also run doc refresh so newly-added
    # or edited markdown files land in `recall docs`.
    _run_doc_ingest(repo, verb="refresh")
    return 0


def cmd_arch(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import arch as _arch
    from claude_almanac.core import config as _app_config
    app_cfg = _app_config.load()
    return _arch.main(
        _repo_or_cwd(args),
        global_send_code_to_llm=app_cfg.content_index.send_code_to_llm,
    )


def cmd_status(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import status as _status
    return _status.main(_repo_or_cwd(args))


DISPATCH = {
    "init": cmd_init,
    "refresh": cmd_refresh,
    "arch": cmd_arch,
    "status": cmd_status,
}


def run(args: argparse.Namespace) -> None:
    fn = DISPATCH.get(args.ci_cmd)
    if fn is None:
        print("usage: claude-almanac content {init|refresh|arch|status}",
              file=sys.stderr)
        sys.exit(2)
    rc = fn(args)
    if rc:
        sys.exit(rc)
