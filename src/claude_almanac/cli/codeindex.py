"""Dispatch `claude-almanac codeindex <init|refresh|arch|status>`."""
from __future__ import annotations

import argparse
import os
import sys


def _repo_or_cwd(args: argparse.Namespace) -> str:
    return args.repo if args.repo else os.getcwd()


def cmd_init(args: argparse.Namespace) -> int:
    from claude_almanac.codeindex import init as _init
    return _init.main(_repo_or_cwd(args))


def cmd_refresh(args: argparse.Namespace) -> int:
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
