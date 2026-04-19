"""`claude-almanac <subcommand>` argparse dispatcher."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-almanac")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show install + daemon status")

    s_setup = sub.add_parser("setup", help="First-run setup")
    s_setup.add_argument("--uninstall", action="store_true")
    s_setup.add_argument("--purge-data", action="store_true")

    s_recall = sub.add_parser("recall", help="Memory recall CLI")
    s_recall.add_argument("subcmd", nargs="?")
    s_recall.add_argument("args", nargs="*")

    return p


def cmd_status(args: argparse.Namespace) -> None:
    from claude_almanac.core import paths
    print("claude-almanac")
    print(f"data_dir:   {paths.data_dir()}")
    print(f"config_dir: {paths.config_dir()}")
    print(f"project:    {paths.project_key()}")


def cmd_setup(args: argparse.Namespace) -> None:
    from . import setup as _setup
    _setup.run(uninstall=args.uninstall, purge_data=args.purge_data)


def cmd_recall(args: argparse.Namespace) -> None:
    from . import recall as _recall
    _recall.run([args.subcmd, *args.args] if args.subcmd else [])


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not ns.cmd:
        parser.print_help()
        sys.exit(1)
    dispatch = {
        "status": cmd_status,
        "setup": cmd_setup,
        "recall": cmd_recall,
    }
    fn = dispatch.get(ns.cmd)
    if fn is None:
        parser.print_help()
        sys.exit(2)
    fn(ns)
