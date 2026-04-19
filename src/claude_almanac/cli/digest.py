"""`claude-almanac digest <subcommand>` dispatcher."""
from __future__ import annotations

import argparse
import sys

from ..digest import generator


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claude-almanac digest")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate today's (or --date) digest")
    g.add_argument("--date", default=None, help="YYYY-MM-DD. Default: today (UTC).")
    g.add_argument("--repo", default=None, help="Restrict to a configured repo alias.")
    g.add_argument("--since", type=int, default=None, help="Window in hours.")
    g.add_argument("--no-notify", action="store_true")
    g.add_argument("--dry-run", action="store_true")

    sub.add_parser("serve", help="Run the digest web UI on 127.0.0.1:8787")
    return p


def run(argv: list[str] | None = None) -> int:
    ns = _build_parser().parse_args(argv)
    if ns.cmd == "generate":
        try:
            result = generator.generate(
                date=ns.date, notify=not ns.no_notify,
                repo_filter=ns.repo, since_hours=ns.since,
                dry_run=ns.dry_run,
            )
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(
            f"wrote {result['digest_path']} "
            f"(+{result['commits_inserted']} commits, "
            f"-{result['pruned']} pruned, "
            f"notified={result['notified']})"
        )
        return 0
    if ns.cmd == "serve":
        # Wired in Task C6
        from ..digest.server import serve as server_serve
        return server_serve()
    print("unknown subcommand", file=sys.stderr)
    return 2
