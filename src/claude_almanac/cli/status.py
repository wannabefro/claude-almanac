"""`claude-almanac status` — richer install/runtime summary."""
from __future__ import annotations

import sqlite3
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from claude_almanac.core import config, paths
from claude_almanac.platform.base import get_scheduler

_UNIT_NAMES = (
    "com.claude-almanac.digest",
    "com.claude-almanac.server",
    "com.claude-almanac.codeindex-refresh",
)


def _package_version() -> str:
    try:
        return _pkg_version("claude-almanac")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _count_archive(db: Path) -> tuple[int, int]:
    if not db.exists():
        return (0, 0)
    conn = sqlite3.connect(str(db))
    try:
        total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        pinned = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE pinned = 1"
        ).fetchone()[0]
        return (int(total), int(pinned))
    except sqlite3.OperationalError:
        return (0, 0)
    finally:
        conn.close()


def _archive_meta(db: Path) -> dict[str, str]:
    if not db.exists():
        return {}
    conn = sqlite3.connect(str(db))
    try:
        return {k: v for k, v in conn.execute("SELECT key, value FROM meta")}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def _most_recent_digest_mtime() -> float | None:
    d = paths.digests_dir()
    if not d.exists():
        return None
    mds = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mds[0].stat().st_mtime if mds else None


def _ollama_reachable(endpoint: str) -> bool:
    try:
        with urlopen(f"{endpoint.rstrip('/')}/api/version", timeout=1) as r:
            return bool(r.status == 200)
    except (URLError, TimeoutError, OSError):
        return False


def _format_ts(epoch: float | None) -> str:
    if epoch is None:
        return "never"
    from datetime import datetime
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _scheduler_lines() -> list[str]:
    try:
        sched = get_scheduler()
    except RuntimeError as e:
        return [f"  (unsupported platform: {e})"]
    lines: list[str] = []
    for name in _UNIT_NAMES:
        try:
            st = sched.status(name)
            lines.append(f"  {name}: {'active' if st.running else 'inactive'}")
        except Exception as e:
            lines.append(f"  {name}: unavailable ({e})")
    return lines


def _embedder_mismatch_warnings(cfg_provider: str, cfg_model: str) -> list[str]:
    warnings: list[str] = []
    candidates = [paths.global_memory_dir() / "archive.db",
                  paths.project_memory_dir() / "archive.db"]
    for db in candidates:
        meta = _archive_meta(db)
        if not meta:
            continue
        if meta.get("embedder") != cfg_provider or meta.get("model") != cfg_model:
            warnings.append(
                f"embedder mismatch in {db}: "
                f"{meta.get('embedder')}/{meta.get('model')} "
                f"(config wants {cfg_provider}/{cfg_model})"
            )
    return warnings


def run() -> None:
    cfg = config.load()
    print(f"claude-almanac {_package_version()}")
    print(f"  data_dir:   {paths.data_dir()}")
    print(f"  config_dir: {paths.config_dir()}")
    print(f"  project:    {paths.project_key()}")
    print()
    g_total, g_pinned = _count_archive(paths.global_memory_dir() / "archive.db")
    p_total, p_pinned = _count_archive(paths.project_memory_dir() / "archive.db")
    print("archive")
    print(f"  global:  {g_total} entries ({g_pinned} pinned)")
    print(f"  project: {p_total} entries ({p_pinned} pinned)")
    print()
    print("digest")
    print(f"  enabled:  {cfg.digest.enabled}")
    print(f"  last run: {_format_ts(_most_recent_digest_mtime())}")
    print()
    print("daemons")
    for line in _scheduler_lines():
        print(line)
    print()
    print("embedder")
    print(f"  provider: {cfg.embedder.provider} ({cfg.embedder.model})")
    endpoint = getattr(cfg.embedder, "endpoint", "http://127.0.0.1:11434")
    if cfg.embedder.provider == "ollama":
        reachable = _ollama_reachable(endpoint)
        print(f"  reachable: {'yes' if reachable else 'no'} ({endpoint})")
    else:
        print("  reachable: (skipped — not Ollama)")
    print()
    print("curator")
    print(f"  provider: {cfg.curator.provider} ({cfg.curator.model})")
    curator_log = paths.logs_dir() / "curator.log"
    if curator_log.exists():
        print(f"  last invocation: {_format_ts(curator_log.stat().st_mtime)}")
    else:
        print("  last invocation: (none yet)")
    print()
    warnings = _embedder_mismatch_warnings(cfg.embedder.provider, cfg.embedder.model)
    print("warnings")
    if warnings:
        for w in warnings:
            print(f"  {w}")
    else:
        print("  (none)")
