"""Runtime config for the digest subsystem.

Adapts `core.config.DigestCfg` into a dataclass the generator + server can
consume, adding window/retention/model knobs that Plan 1 kept out of
Config (they rarely change and belong to digest-only concerns).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_almanac.core import config as core_config
from claude_almanac.core import paths


class ConfigError(ValueError):
    """Raised when digest config is unusable for a generator run."""


@dataclass(frozen=True)
class RepoEntry:
    path: str
    name: str


@dataclass(frozen=True)
class DigestRuntimeConfig:
    repos: list[RepoEntry]
    window_hours: int
    retention_days: int
    haiku_model: str
    notification: bool
    digest_dir: str
    activity_db: str


def from_core_config(
    cfg: core_config.Config,
    *,
    window_hours: int = 24,
    retention_days: int = 30,
    haiku_model: str = "haiku",
) -> DigestRuntimeConfig:
    if not cfg.digest.repos:
        raise ConfigError(
            "digest.repos is empty; add at least one repo to config.yaml "
            "before running `claude-almanac digest generate`"
        )
    repos = [
        RepoEntry(path=str(Path(r.path).expanduser()), name=r.alias)
        for r in cfg.digest.repos
    ]
    return DigestRuntimeConfig(
        repos=repos,
        window_hours=window_hours,
        retention_days=retention_days,
        haiku_model=haiku_model,
        notification=cfg.digest.notify,
        digest_dir=str(paths.digests_dir()),
        activity_db=str(paths.data_dir() / "activity.db"),
    )
