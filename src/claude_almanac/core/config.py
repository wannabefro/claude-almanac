"""Config schema and YAML I/O. config.yaml lives under config_dir()."""
from __future__ import annotations

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


@dataclass
class RetrievalCfg:
    top_k: int = 5
    code_autoinject: bool = True


@dataclass
class ThresholdsCfg:
    dedup_distance: float | None = None  # None -> use embedder profile default


@dataclass
class Config:
    embedder: EmbedderCfg = field(default_factory=EmbedderCfg)
    digest: DigestCfg = field(default_factory=DigestCfg)
    code_index: CodeIndexCfg = field(default_factory=CodeIndexCfg)
    retrieval: RetrievalCfg = field(default_factory=RetrievalCfg)
    thresholds: ThresholdsCfg = field(default_factory=ThresholdsCfg)


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


def save(cfg: Config) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        yaml.safe_dump(asdict(cfg), f, sort_keys=False)


def _from_dict(raw: dict[str, Any]) -> Config:
    emb = raw.get("embedder", {})
    dig = raw.get("digest", {})
    repos = [RepoCfg(**r) for r in dig.get("repos", [])]
    return Config(
        embedder=EmbedderCfg(**emb),
        digest=DigestCfg(
            enabled=dig.get("enabled", False),
            repos=repos,
            hour=dig.get("hour", 7),
            notify=dig.get("notify", True),
        ),
        code_index=CodeIndexCfg(**raw.get("code_index", {})),
        retrieval=RetrievalCfg(**raw.get("retrieval", {})),
        thresholds=ThresholdsCfg(**raw.get("thresholds", {})),
    )
