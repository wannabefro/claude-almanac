"""`claude-almanac setup` — idempotent install/uninstall for dirs, config,
and platform daemons."""
from __future__ import annotations

import contextlib
import os
import shutil
import sys
from pathlib import Path

import httpx
import yaml

from claude_almanac.core import config as core_config
from claude_almanac.core import paths
from claude_almanac.core.config import CuratorCfg
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


def _ollama_reachable() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=3.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _ollama_pull(model: str) -> None:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    with httpx.stream(
        "POST",
        f"{host.rstrip('/')}/api/pull",
        json={"name": model},
        timeout=httpx.Timeout(connect=5.0, read=600.0, write=30.0, pool=30.0),
    ) as r:
        for line in r.iter_lines():
            if not line:
                continue
            sys.stdout.write(f"  pull: {line[:120]}\n")
            sys.stdout.flush()


def _migrate_curator_provider() -> None:
    """Idempotent curator provider configuration.

    - If the YAML has no ``curator:`` block: pick a provider based on env.
    - If it has one with ``provider=ollama``: re-run pull to self-heal.
    - Otherwise: leave it alone (user choice wins).
    """
    path = core_config.config_path()
    raw: dict[str, object] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
    has_block = "curator" in raw
    cfg = core_config.load()

    if not has_block:
        if os.environ.get("ANTHROPIC_API_KEY"):
            cfg.curator = CuratorCfg(
                provider="anthropic_sdk",
                model="claude-haiku-4-5-20251001",
            )
            print(
                "curator: anthropic_sdk / claude-haiku-4-5-20251001"
                " (fast API path, key found in env)"
            )
        else:
            cfg.curator = CuratorCfg(provider="ollama", model="gemma3:4b")
            if _ollama_reachable():
                print("curator: ollama / gemma3:4b (local) — pulling model...")
                try:
                    _ollama_pull("gemma3:4b")
                except httpx.HTTPError as e:
                    print(f"  warning: ollama pull failed: {e}")
            else:
                print(
                    "curator: ollama / gemma3:4b (local) — warning: Ollama"
                    " unreachable; curator will no-op until Ollama is running"
                    " and the model is pulled"
                )
        core_config.save(cfg)
        return

    # Block exists — respect user choice, but self-heal ollama pulls.
    if cfg.curator.provider == "ollama" and _ollama_reachable():
        try:
            _ollama_pull(cfg.curator.model)
        except httpx.HTTPError as e:
            print(f"  warning: ollama pull failed: {e}")


def _print_provider_suggestions() -> None:
    """Info-only: note which curator providers are available on this machine.

    Doesn't change config — users pick per-surface overrides
    (rollup.provider, digest.narrative_provider, digest.qa_provider)
    themselves. This just surfaces the option so users don't have to
    discover claude_cli/codex providers from docs alone.
    """
    available: list[str] = []
    if shutil.which("claude"):
        available.append(
            "  claude_cli — uses `claude` CLI (OAuth, no API key needed)"
        )
    if shutil.which("codex"):
        available.append(
            "  codex      — uses `codex exec` (OAuth, no API key needed)"
        )
    if os.environ.get("ANTHROPIC_API_KEY"):
        available.append(
            "  anthropic_sdk — direct SDK via ANTHROPIC_API_KEY (fastest)"
        )
    if not available:
        return
    print()
    print("additional curator providers available on this machine:")
    for line in available:
        print(line)
    print(
        "  (configure per-surface via rollup.provider / "
        "digest.narrative_provider / digest.qa_provider in config.yaml)"
    )


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
    _migrate_curator_provider()
    _print_provider_suggestions()
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
