"""`claude-almanac setup` — idempotent install/uninstall for dirs, config,
and platform daemons."""
from __future__ import annotations

import shutil
import sys

from ..core import config as core_config
from ..core import paths
from ..embedders import make_embedder
from ..platform import get_scheduler


DIGEST_UNIT_NAME = "com.claude-almanac.digest"


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
    cfg = core_config.load()
    ok = _probe_embedder()
    if ok:
        print("embedder reachable")
    if cfg.digest.enabled:
        print("digest subsystem not available in v0.1 — skipping daemon install")
        print("enable digest in a future release")
    print("setup complete. next: add repos to digest.repos in config.yaml")


def _do_uninstall(*, purge_data: bool) -> None:
    scheduler = get_scheduler()
    scheduler.uninstall(DIGEST_UNIT_NAME)
    scheduler.uninstall("com.claude-almanac.server")
    print("uninstalled platform units")
    if purge_data:
        ans = input(f"delete all data under {paths.data_dir()}? type 'yes': ")
        if ans.strip().lower() == "yes":
            if paths.data_dir().exists():
                shutil.rmtree(paths.data_dir())
                print(f"removed {paths.data_dir()}")
