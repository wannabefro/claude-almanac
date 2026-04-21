"""Config schema and YAML I/O. config.yaml lives under config_dir()."""
from __future__ import annotations

import dataclasses
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import paths


@dataclass
class EmbedderCfg:
    provider: str = "ollama"
    model: str = "bge-m3"
    api_key_env: str | None = None


@dataclass
class CuratorCfg:
    provider: str = "ollama"              # "ollama" | "anthropic_sdk"
    model: str = "gemma3:4b"               # or "claude-haiku-4-5-20251001"
    timeout_s: int = 0                     # 0 -> provider default


@dataclass
class RepoCfg:
    path: str
    alias: str


@dataclass
class DigestCfg:
    enabled: bool = False
    repos: list[RepoCfg] = field(default_factory=list)
    hour: int = 7
    notify: bool = True


@dataclass
class CodeIndexCfg:
    enabled: bool = False
    send_code_to_llm: bool = False
    daily_refresh: bool = False
    refresh_hour: int = 4


@dataclass
class DecayCfg:
    enabled: bool = True
    half_life_days: int = 60
    use_count_exponent: float = 0.6
    band: float = 0.0
    prune_threshold: float = 0.05
    prune_min_age_days: int = 30


@dataclass
class RollupRetrievalCfg:
    """Settings for rollup retrieval (memory synthesis)."""
    autoinject: bool = False
    topk: int = 1
    distance_cutoff: float = 0.4
    # Rollups have longer half-life than entries since they're narrative substrate.
    half_life_days: int = 30
    use_count_exponent: float = 0.5


@dataclass
class EdgesRetrievalCfg:
    """Settings for knowledge-graph edge expansion (related entries)."""
    expand: bool = False
    expand_hops: int = 1
    expand_bonus: float = 0.25
    skip_superseded: bool = True


@dataclass
class RetrievalCfg:
    top_k: int = 5
    code_autoinject: bool = True
    decay: DecayCfg = field(default_factory=DecayCfg)
    rollups: RollupRetrievalCfg = field(default_factory=RollupRetrievalCfg)
    edges: EdgesRetrievalCfg = field(default_factory=EdgesRetrievalCfg)


@dataclass
class ThresholdsCfg:
    dedup_distance: float | None = None  # None -> use embedder profile default


@dataclass
class RollupCfg:
    """Settings for rollup generation and curation."""
    enabled: bool = True
    idle_threshold_minutes: int = 45
    max_transcript_tokens: int = 32000
    # None -> defaults to curator provider, or anthropic_sdk if API key set
    provider: str | None = None
    min_turns: int = 3


@dataclass
class Config:
    embedder: EmbedderCfg = field(default_factory=EmbedderCfg)
    curator: CuratorCfg = field(default_factory=CuratorCfg)
    digest: DigestCfg = field(default_factory=DigestCfg)
    code_index: CodeIndexCfg = field(default_factory=CodeIndexCfg)
    retrieval: RetrievalCfg = field(default_factory=RetrievalCfg)
    thresholds: ThresholdsCfg = field(default_factory=ThresholdsCfg)
    rollup: RollupCfg = field(default_factory=RollupCfg)
    auto_upgrade: bool = False


CONFIG_FILENAME = "config.yaml"


def default_config() -> Config:
    return Config()


def config_path() -> Path:
    return paths.config_dir() / CONFIG_FILENAME


def load() -> Config:
    p = config_path()
    if not p.exists():
        return default_config()
    with p.open() as f:
        raw = yaml.safe_load(f) or {}
    return _from_dict(raw)


def load_config_from_text(text: str) -> Config:
    """Parse config YAML from text (for tests + programmatic use)."""
    raw = yaml.safe_load(text) or {}
    return _from_dict(raw)


def save(cfg: Config) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        yaml.safe_dump(asdict(cfg), f, sort_keys=False)


def _code_index_from_dict(raw: dict[str, Any]) -> CodeIndexCfg:
    return CodeIndexCfg(
        enabled=raw.get("enabled", False),
        send_code_to_llm=raw.get("send_code_to_llm", False),
        daily_refresh=raw.get("daily_refresh", False),
        refresh_hour=raw.get("refresh_hour", 4),
    )


def _from_dict(raw: dict[str, Any]) -> Config:
    emb = raw.get("embedder", {})
    dig = raw.get("digest", {})
    repos = [RepoCfg(**r) for r in dig.get("repos", [])]
    curator_raw = raw.get("curator", {})
    curator = CuratorCfg(
        provider=curator_raw.get("provider", "ollama"),
        model=curator_raw.get("model", "gemma3:4b"),
        timeout_s=curator_raw.get("timeout_s", 0),
    )
    retrieval_raw = raw.get("retrieval") or {}
    decay_raw = retrieval_raw.get("decay") or {}
    rollups_raw = retrieval_raw.get("rollups") or {}
    edges_raw = retrieval_raw.get("edges") or {}
    retrieval = RetrievalCfg(
        top_k=retrieval_raw.get("top_k", 5),
        code_autoinject=retrieval_raw.get("code_autoinject", True),
        decay=DecayCfg(
            enabled=decay_raw.get("enabled", True),
            half_life_days=decay_raw.get("half_life_days", 60),
            use_count_exponent=decay_raw.get("use_count_exponent", 0.6),
            band=decay_raw.get("band", 0.0),
            prune_threshold=decay_raw.get("prune_threshold", 0.05),
            prune_min_age_days=decay_raw.get("prune_min_age_days", 30),
        ),
        rollups=RollupRetrievalCfg(
            autoinject=rollups_raw.get("autoinject", False),
            topk=rollups_raw.get("topk", 1),
            distance_cutoff=rollups_raw.get("distance_cutoff", 0.4),
            half_life_days=rollups_raw.get("half_life_days", 30),
            use_count_exponent=rollups_raw.get("use_count_exponent", 0.5),
        ),
        edges=EdgesRetrievalCfg(
            expand=edges_raw.get("expand", False),
            expand_hops=edges_raw.get("expand_hops", 1),
            expand_bonus=edges_raw.get("expand_bonus", 0.25),
            skip_superseded=edges_raw.get("skip_superseded", True),
        ),
    )

    rollup_raw = raw.get("rollup") or {}
    rollup_cfg = RollupCfg(
        enabled=rollup_raw.get("enabled", True),
        idle_threshold_minutes=rollup_raw.get("idle_threshold_minutes", 45),
        max_transcript_tokens=rollup_raw.get("max_transcript_tokens", 32000),
        provider=rollup_raw.get("provider"),  # None by default
        min_turns=rollup_raw.get("min_turns", 3),
    )

    cfg = Config(
        embedder=EmbedderCfg(**emb),
        curator=curator,
        digest=DigestCfg(
            enabled=dig.get("enabled", False),
            repos=repos,
            hour=dig.get("hour", 7),
            notify=dig.get("notify", True),
        ),
        code_index=_code_index_from_dict(raw.get("code_index", {})),
        retrieval=retrieval,
        thresholds=ThresholdsCfg(**raw.get("thresholds", {})),
        rollup=rollup_cfg,
        auto_upgrade=raw.get("auto_upgrade", False),
    )

    # Apply ANTHROPIC_API_KEY auto-default for rollup.provider
    if cfg.rollup.provider is None and os.environ.get("ANTHROPIC_API_KEY"):
        cfg = dataclasses.replace(
            cfg,
            rollup=dataclasses.replace(cfg.rollup, provider="anthropic_sdk"),
        )

    return cfg


def materialize_missing_fields() -> bool:
    """Load config.yaml and rewrite it with any fields that were missing
    (filled with defaults). Returns True if the file was modified. Does nothing
    if the file doesn't exist or is already canonical."""
    p = config_path()
    if not p.exists():
        return False
    cfg = load()
    canonical = yaml.safe_dump(asdict(cfg), sort_keys=False)
    current = p.read_text()
    if canonical == current:
        return False
    p.write_text(canonical)
    return True
