"""`claude-almanac <subcommand>` argparse dispatcher."""
from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version


def _package_version() -> str:
    try:
        return _pkg_version("claude-almanac")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-almanac")
    p.add_argument(
        "--version",
        action="version",
        version=f"claude-almanac {_package_version()}",
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show install + daemon status")

    s_setup = sub.add_parser("setup", help="First-run setup")
    s_setup.add_argument("--uninstall", action="store_true")
    s_setup.add_argument("--purge-data", action="store_true")

    s_recall = sub.add_parser("recall", help="Memory recall CLI")
    s_recall.add_argument("subcmd", nargs="?")
    s_recall.add_argument("args", nargs="*")

    s_digest = sub.add_parser("digest", help="Digest generate/serve")
    s_digest.add_argument("subcmd", nargs="?")
    s_digest.add_argument("args", nargs="*")

    s_ci = sub.add_parser("codeindex", help="Code-index subsystem")
    ci_sub = s_ci.add_subparsers(dest="ci_cmd")
    for name, help_ in (
        ("init",    "Initial symbol indexing for the current repo"),
        ("refresh", "Incremental re-index against origin's default branch"),
        ("arch",    "Module-level arch summaries (requires send_code_to_llm)"),
        ("status",  "Show DB health and dirty-module queue"),
    ):
        sp = ci_sub.add_parser(name, help=help_)
        sp.add_argument("--repo", default=None,
                        help="Repo root; defaults to current working directory")
        if name == "refresh":
            sp.add_argument("--all", dest="all_repos", action="store_true",
                            help="Refresh every repo listed in code_index.repos "
                                 "(auto-init missing DBs). Overrides --repo.")

    s_cal = sub.add_parser("calibrate", help="Embedder calibration helper")
    s_cal.add_argument("args", nargs="*")

    s_reembed = sub.add_parser(
        "migrate-embedder",
        help="Re-embed every archive.db + rollups_vec to the configured embedder "
             "(preserves all entry metadata, histories, and edges)",
    )
    s_reembed.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without touching any DB",
    )

    s_tail = sub.add_parser("tail", help="Stream merged logs across subsystems")
    follow = s_tail.add_mutually_exclusive_group()
    follow.add_argument("--follow", dest="follow", action="store_true",
                        default=True, help="Keep tailing after backfill (default)")
    follow.add_argument("--no-follow", dest="follow", action="store_false",
                        help="Print backfill lines and exit")
    s_tail.add_argument("--lines", type=int, default=50,
                        help="Max lines to backfill per source (default 50)")
    s_tail.add_argument("--since", default=None,
                        help="Time window for backfill, e.g. 10m|1h|2d")
    s_tail.add_argument("--source", action="append", default=None,
                        choices=("curator", "code-index", "digest", "server"),
                        help="Restrict to one or more sources (repeatable)")

    return p


def cmd_status(args: argparse.Namespace) -> None:
    from . import status as _status
    _status.run()


def cmd_setup(args: argparse.Namespace) -> None:
    from . import setup as _setup
    _setup.run(uninstall=args.uninstall, purge_data=args.purge_data)


def cmd_recall(args: argparse.Namespace) -> None:
    from . import recall as _recall
    _recall.run([args.subcmd, *args.args] if args.subcmd else [])


def cmd_codeindex(args: argparse.Namespace) -> None:
    from . import codeindex as _ci
    _ci.run(args)


def cmd_digest(args: argparse.Namespace) -> None:
    from . import digest as _digest
    sys.exit(_digest.run([args.subcmd, *args.args] if args.subcmd else []))


def cmd_calibrate(args: argparse.Namespace) -> None:
    from . import calibrate as _cal
    _cal.run(list(args.args))


def cmd_migrate_embedder(args: argparse.Namespace) -> None:
    from claude_almanac.core import reembed
    raise SystemExit(reembed.run(dry_run=bool(args.dry_run)))


def cmd_tail(args: argparse.Namespace) -> None:
    from . import tail as _tail
    argv: list[str] = []
    argv.append("--follow" if args.follow else "--no-follow")
    argv += ["--lines", str(args.lines)]
    if args.since:
        argv += ["--since", args.since]
    for s in args.source or []:
        argv += ["--source", s]
    _tail.run(argv)


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
        "digest": cmd_digest,
        "codeindex": cmd_codeindex,
        "migrate-embedder": cmd_migrate_embedder,
        "calibrate": cmd_calibrate,
        "tail": cmd_tail,
    }
    fn = dispatch.get(ns.cmd)
    if fn is None:
        parser.print_help()
        sys.exit(2)
    fn(ns)


if __name__ == "__main__":
    main()
