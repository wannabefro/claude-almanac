"""`claude-almanac setup` — idempotent install/uninstall for dirs, config,
and platform daemons."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
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
CONTENTINDEX_UNIT_NAME = "com.claude-almanac.contentindex-refresh"
# Legacy name installed by v0.3.x; setup removes it on upgrade.
LEGACY_CODEINDEX_UNIT_NAME = "com.claude-almanac.codeindex-refresh"


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


def _ensure_embedder_pulled() -> None:
    """Pull the configured Ollama embedder model if it isn't already local.

    Fresh installs (and v0.3.9 upgrade from bge-m3 → qwen3-embedding) rely on
    the model being present in Ollama. Skip silently for non-Ollama providers
    and when Ollama isn't reachable — those surface their own errors on first use.
    """
    cfg = core_config.load()
    if cfg.embedder.provider != "ollama":
        return
    if not _ollama_reachable():
        return
    model = cfg.embedder.model
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    # Ollama's /api/tags lists locally-pulled models. Probe before pulling so
    # we don't spam progress output every setup run.
    try:
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=3.0)
        tags = {m.get("name", "") for m in (r.json().get("models") or [])}
    except (httpx.HTTPError, ValueError, KeyError):
        tags = set()
    if model in tags or f"{model}:latest" in tags:
        return
    print(f"embedder: ollama / {model} — pulling model...")
    try:
        _ollama_pull(model)
    except httpx.HTTPError as e:
        print(f"  warning: ollama pull failed: {e}")


def _migrate_all_archives() -> None:
    """Walk every project + global archive.db and run ensure_schema on each.

    Older worktrees / orphaned project dirs may hold archive.db files that
    pre-date v0.3.1's `last_used_at` / `use_count` columns or v0.3.2's
    rollups + edges tables. If any such DB is ever touched by a code path
    expecting current schema (recall search-all being the common one), the
    query fails with `no such column`. Running ensure_schema on every DB
    during setup auto-heals them before any retrieval path sees them.
    """
    from claude_almanac.core import archive
    from claude_almanac.embedders.profiles import get as get_profile

    cfg = core_config.load()
    try:
        profile = get_profile(cfg.embedder.provider, cfg.embedder.model)
    except KeyError:
        # No known profile for the configured embedder — skip migration; user
        # probably needs to fix config before anything works anyway.
        return

    candidate_dbs: list[Path] = []
    # Global scope
    global_db = paths.global_memory_dir() / "archive.db"
    if global_db.exists():
        candidate_dbs.append(global_db)
    # All project scopes (worktrees, cwd-hashed, git-hashed)
    projs = paths.projects_memory_dir()
    if projs.exists():
        for d in projs.iterdir():
            if d.is_dir():
                db = d / "archive.db"
                if db.exists():
                    candidate_dbs.append(db)

    fixed = 0
    for db in candidate_dbs:
        try:
            conn = archive._connect(db)
        except Exception:
            continue
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(entries)").fetchall()}
            # Quick probe: v0.3.1+ has last_used_at, v0.3.2+ has edges table
            needs_migration = (
                "last_used_at" not in cols
                or conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='edges'"
                ).fetchone() is None
            )
            if not needs_migration:
                continue
            archive.ensure_schema(conn, profile=profile)
            fixed += 1
        except Exception as e:
            print(f"  warning: failed to migrate {db}: {e}", file=sys.stderr)
        finally:
            conn.close()

    if fixed:
        print(f"migrated {fixed} archive DB(s) to current schema")


def _migrate_all_code_indexes() -> None:
    """Walk every project's content-index.db and rename stale ones aside.

    A content-index.db's `entries_vec` virtual table pins the embedding
    dimension at creation time (FLOAT[N]). If the embedder's dim changes
    (bge-m3 swap, model upgrade, or a legacy default-2 wrong-dim bug from
    old installs), every upsert / query fails with
    `sqlite3.OperationalError: Dimension mismatch`.

    We can't migrate vectors across dims — the embeddings have to be
    recomputed. This helper renames any mismatched content-index.db to
    `content-index.db.stale-<detected-dim>` so the user can inspect or
    discard, then prints a one-line note pointing them at
    `claude-almanac content init`.
    """
    from claude_almanac.embedders.profiles import get as get_profile

    cfg = core_config.load()
    try:
        profile = get_profile(cfg.embedder.provider, cfg.embedder.model)
    except KeyError:
        return
    expected_dim = profile.dim

    candidate_dbs: list[Path] = []
    projs = paths.projects_memory_dir()
    if projs.exists():
        for d in projs.iterdir():
            if d.is_dir():
                db = d / "content-index.db"
                if db.exists():
                    candidate_dbs.append(db)

    renamed = 0
    for db in candidate_dbs:
        detected = _detect_code_index_dim(db)
        if detected is None or detected == expected_dim:
            continue
        stale = db.with_name(f"content-index.db.stale-{detected}")
        try:
            db.rename(stale)
        except OSError as e:
            print(f"  warning: could not rename {db} → {stale}: {e}",
                  file=sys.stderr)
            continue
        renamed += 1
        print(
            f"moved {db} → {stale.name} (dim={detected}, expected={expected_dim})"
        )

    if renamed:
        print(
            f"renamed {renamed} stale content-index DB(s); "
            "run `claude-almanac content init` in the affected repo(s) to rebuild"
        )


def _detect_code_index_dim(db: Path) -> int | None:
    """Pull the FLOAT[N] literal out of the entries_vec CREATE VIRTUAL TABLE SQL.

    Returns None when the DB is unreadable or the entries_vec table is missing.
    """
    import re
    import sqlite3

    try:
        conn = sqlite3.connect(db)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entries_vec'"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None or not row[0]:
        return None
    match = re.search(r"FLOAT\[(\d+)\]", row[0])
    if not match:
        return None
    return int(match.group(1))


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


def _reinstall_units_under_new_names() -> None:
    """Remove legacy v0.3.x unit names so the new contentindex-named units
    take their place.

    v0.4 renames the `com.claude-almanac.codeindex-refresh` unit to
    `com.claude-almanac.contentindex-refresh`. We can't migrate the launchd
    plist / systemd unit in place (the program path also changed: `codeindex
    refresh` → `content refresh`), so the safest sequence is:

      1. best-effort uninstall of the legacy unit (no-op if never installed)
      2. the installer below registers the new-named unit fresh

    The new install happens later in `_do_install`, so this helper is
    idempotent and cheap to run every setup.
    """
    try:
        sched = get_scheduler()
    except Exception:
        return
    # Narrow suppression — we want to silence "unit doesn't exist" /
    # "not installed" failures from launchd/systemd, not real permission
    # or OOM / unexpected exceptions. If the legacy uninstall raises
    # something outside this set, surface it so the upgrade path is
    # debuggable instead of silently half-done.
    with contextlib.suppress(FileNotFoundError, OSError, subprocess.SubprocessError):
        sched.uninstall(LEGACY_CODEINDEX_UNIT_NAME)


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
    _ensure_embedder_pulled()
    _migrate_all_archives()
    _migrate_all_code_indexes()
    _print_provider_suggestions()
    cfg = core_config.load()
    _stamp_installed_version()
    ok = _probe_embedder()
    if ok:
        print("embedder reachable")
    scheduler = get_scheduler() if (
        cfg.digest.enabled or cfg.content_index.daily_refresh
    ) else None
    _reinstall_units_under_new_names()
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
    if cfg.content_index.daily_refresh:
        assert scheduler is not None
        if not cfg.digest.repos:
            print("content_index.daily_refresh: true but digest.repos is empty; "
                  "skipping install")
        else:
            scheduler.install_daily(
                CONTENTINDEX_UNIT_NAME,
                [sys.executable, "-m", "claude_almanac.cli.main",
                 "content", "refresh", "--all"],
                cfg.content_index.refresh_hour,
            )
            print(f"installed daily contentindex refresh unit: {CONTENTINDEX_UNIT_NAME} "
                  f"(hour={cfg.content_index.refresh_hour}, "
                  f"repos={len(cfg.digest.repos)})")
    else:
        # Clean up the unit if the user just toggled the flag off.
        with contextlib.suppress(Exception):
            (scheduler or get_scheduler()).uninstall(CONTENTINDEX_UNIT_NAME)
    print("setup complete. next: add repos to digest.repos in config.yaml")


def _do_uninstall(*, purge_data: bool) -> None:
    scheduler = get_scheduler()
    scheduler.uninstall(DIGEST_UNIT_NAME)
    scheduler.uninstall("com.claude-almanac.server")
    scheduler.uninstall(CONTENTINDEX_UNIT_NAME)
    # Best-effort remove the legacy v0.3.x unit too so a clean uninstall
    # doesn't leave orphan launchd/systemd jobs behind.
    with contextlib.suppress(Exception):
        scheduler.uninstall(LEGACY_CODEINDEX_UNIT_NAME)
    print("uninstalled platform units")
    if purge_data:
        ans = input(f"delete all data under {paths.data_dir()}? type 'yes': ")
        if ans.strip().lower() == "yes" and paths.data_dir().exists():
            shutil.rmtree(paths.data_dir())
            print(f"removed {paths.data_dir()}")
