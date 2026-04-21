"""Dispatch `claude-almanac codeindex <init|refresh|arch|status>`."""
from __future__ import annotations

import argparse
import os
import pathlib
import sys


def _repo_or_cwd(args: argparse.Namespace) -> str:
    return args.repo if args.repo else os.getcwd()


def cmd_init(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import init as _init
    return _init.main(_repo_or_cwd(args))


def _refresh_one(repo_path: str) -> int:
    """Refresh a single repo. Run init first when the DB is missing so a
    brand-new entry in code_index.repos doesn't require a manual bootstrap.
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
        return _refresh.main(repo_path)
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
    return _refresh.main(_repo_or_cwd(args))


def cmd_arch(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import arch as _arch
    from claude_almanac.core import config as _app_config
    app_cfg = _app_config.load()
    return _arch.main(
        _repo_or_cwd(args),
        global_send_code_to_llm=app_cfg.code_index.send_code_to_llm,
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
        print("usage: claude-almanac codeindex {init|refresh|arch|status}",
              file=sys.stderr)
        sys.exit(2)
    rc = fn(args)
    if rc:
        sys.exit(rc)
