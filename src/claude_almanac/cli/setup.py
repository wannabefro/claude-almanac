"""`claude-almanac setup` — idempotent install/uninstall for dirs, config,
and platform daemons."""
from __future__ import annotations

import contextlib
import shutil
import sys
from pathlib import Path

from claude_almanac.core import config as core_config
from claude_almanac.core import paths
from claude_almanac.embedders import make_embedder
from claude_almanac.platform import get_scheduler

DIGEST_UNIT_NAME = "com.claude-almanac.digest"
DIGEST_SERVER_UNIT_NAME = "com.claude-almanac.server"
CODEINDEX_UNIT_NAME = "com.claude-almanac.codeindex-refresh"


def _installed_version() -> str:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version
    try:
        return _pkg_version("claude-almanac")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _version_stamp_path() -> Path:
    return paths.data_dir() / ".installed_version"


def _stamp_installed_version() -> None:
    stamp = _version_stamp_path()
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(_installed_version())


def _probe_embedder() -> bool:
    try:
        cfg = core_config.load()
        emb = make_embedder(cfg.embedder.provider, cfg.embedder.model)
        emb.embed(["probe"])
        return True
    except Exception as e:
        print(f"warning: embedder unreachable: {e}", file=sys.stderr)
        return False


def run(*, uninstall: bool, purge_data: bool) -> None:
    if uninstall:
        _do_uninstall(purge_data=purge_data)
        return
    _do_install()


def _do_install() -> None:
    paths.ensure_dirs()
    cfg_path = core_config.config_path()
    if not cfg_path.exists():
        core_config.save(core_config.default_config())
        print(f"wrote default config to {cfg_path}")
    elif core_config.materialize_missing_fields():
        print(f"updated {cfg_path} with new default fields")
    cfg = core_config.load()
    _stamp_installed_version()
    ok = _probe_embedder()
    if ok:
        print("embedder reachable")
    scheduler = get_scheduler() if (
        cfg.digest.enabled or cfg.code_index.daily_refresh
    ) else None
    if cfg.digest.enabled:
        assert scheduler is not None
        scheduler.install_daily(
            DIGEST_UNIT_NAME,
            [sys.executable, "-m", "claude_almanac.cli.main",
             "digest", "generate"],
            cfg.digest.hour,
        )
        print(f"installed daily digest unit: {DIGEST_UNIT_NAME}")
        scheduler.install_always_on(
            DIGEST_SERVER_UNIT_NAME,
            [sys.executable, "-m", "claude_almanac.cli.main",
             "digest", "serve"],
        )
        print(f"installed digest server unit: {DIGEST_SERVER_UNIT_NAME}")
    else:
        print("digest disabled (set digest.enabled: true in config.yaml to enable)")
    if cfg.code_index.daily_refresh:
        assert scheduler is not None
        if not cfg.digest.repos:
            print("code_index.daily_refresh: true but digest.repos is empty; "
                  "skipping install")
        else:
            scheduler.install_daily(
                CODEINDEX_UNIT_NAME,
                [sys.executable, "-m", "claude_almanac.cli.main",
                 "codeindex", "refresh", "--all"],
                cfg.code_index.refresh_hour,
            )
            print(f"installed daily codeindex refresh unit: {CODEINDEX_UNIT_NAME} "
                  f"(hour={cfg.code_index.refresh_hour}, "
                  f"repos={len(cfg.digest.repos)})")
    else:
        # Clean up the unit if the user just toggled the flag off.
        with contextlib.suppress(Exception):
            (scheduler or get_scheduler()).uninstall(CODEINDEX_UNIT_NAME)
    print("setup complete. next: add repos to digest.repos in config.yaml")


def _do_uninstall(*, purge_data: bool) -> None:
    scheduler = get_scheduler()
    scheduler.uninstall(DIGEST_UNIT_NAME)
    scheduler.uninstall("com.claude-almanac.server")
    scheduler.uninstall(CODEINDEX_UNIT_NAME)
    print("uninstalled platform units")
    if purge_data:
        ans = input(f"delete all data under {paths.data_dir()}? type 'yes': ")
        if ans.strip().lower() == "yes" and paths.data_dir().exists():
            shutil.rmtree(paths.data_dir())
            print(f"removed {paths.data_dir()}")
