"""Per-repo code-index config + module discovery.

Reads <repo_root>/.claude/code-index.yaml. See spec §code_index.
"""
from __future__ import annotations

import glob
import json
import os
import pathlib
from dataclasses import dataclass, field

import yaml

DEFAULT_EXCLUDES = [
    "**/node_modules/**",
    "**/.venv/**",
    "**/.terraform/**",
    "**/.terragrunt-cache/**",
    "**/dist/**",
    "**/build/**",
    # TypeScript build-output trees. `.output/` is the Nuxt/Nitro convention
    # and shows up alongside `dist/` in many frontend monorepos. Generated
    # `.d.ts` declarations re-state signatures already present in the
    # source `.ts`, so indexing them doubles every symbol hit (observed
    # on 2026-04-21 with Calendar.types.d.ts duplicating Calendar.types.ts
    # in the top-3 slots).
    "**/.output/**",
    "**/*.d.ts",
    "**/*_generated.*",
    "**/__pycache__/**",
    "**/*.egg-info/**",
    "**/_static/**",
    "**/_build/**",
]

MAX_FILE_BYTES = 256 * 1024

SERENA_EXTS = {"py", "ts", "tsx", "js", "jsx", "go", "java", "rs"}

DEFAULT_DOC_PATTERNS = [
    "docs/**",
    "README.md",
    "CHANGELOG.md",
    "*.md",
]

DEFAULT_DOC_EXCLUDES: list[str] = []  # stacks on DEFAULT_EXCLUDES


class ConfigError(Exception):
    pass


@dataclass
class DocsCfg:
    """v0.4 per-repo documents-subsystem config (``docs:`` block in
    ``.claude/code-index.yaml`` — renamed to ``content-index.yaml`` in
    Task 7). Defaults aim to match the common case: index ``docs/``,
    top-level READMEs + CHANGELOGs, and any markdown at the repo root,
    with modestly sized chunks suited to ~2KB bodies.
    """
    enabled: bool = True
    patterns: list[str] = field(default_factory=lambda: list(DEFAULT_DOC_PATTERNS))
    extra_excludes: list[str] = field(default_factory=list)
    chunk_max_chars: int = 2000
    chunk_overlap_chars: int = 200


@dataclass
class Config:
    repo_root: str
    default_branch: str
    discovery_mode: str              # 'auto' | 'patterns'
    patterns: list[str]
    extra_patterns: list[str]
    extra_excludes: list[str]
    send_code_to_llm: bool
    min_files_for_arch: int
    docs: DocsCfg = field(default_factory=DocsCfg)

    @property
    def excludes(self) -> list[str]:
        return DEFAULT_EXCLUDES + list(self.extra_excludes)


@dataclass(frozen=True)
class Module:
    name: str
    path: str


def load(repo_root: str) -> Config:
    root = pathlib.Path(repo_root).resolve()
    cfg_path = root / ".claude" / "code-index.yaml"
    if not cfg_path.exists():
        raise ConfigError(f"no .claude/code-index.yaml at {root}")
    data = yaml.safe_load(cfg_path.read_text())
    if data is None:
        raise ConfigError("code-index.yaml is empty; expected a mapping")
    if not isinstance(data, dict):
        raise ConfigError("code-index.yaml must be a mapping at the top level")
    if "default_branch" not in data:
        raise ConfigError("default_branch is required in code-index.yaml")

    default_branch = data["default_branch"]
    modules = data.get("modules") or {}
    if not isinstance(modules, dict):
        modules = {}
    has_from = "from" in modules
    has_patterns = "patterns" in modules
    if has_from and has_patterns:
        raise ConfigError("cannot set both 'from' and 'patterns' in modules")
    if not has_from and not has_patterns:
        raise ConfigError("must set either 'from' or 'patterns' in modules")

    if has_from:
        from_value = modules["from"]
        if from_value != "auto":
            raise ConfigError(f"only 'from: auto' is supported; got 'from: {from_value}'")
        discovery_mode = "auto"
        patterns: list[str] = []
    else:
        discovery_mode = "patterns"
        raw_patterns = modules.get("patterns")
        if raw_patterns is not None and not isinstance(raw_patterns, list):
            raise ConfigError("code-index.yaml modules.patterns must be a list")
        patterns = list(raw_patterns or [])

    docs_cfg = _parse_docs_cfg(data.get("docs"))

    return Config(
        repo_root=str(root),
        default_branch=default_branch,
        discovery_mode=discovery_mode,
        patterns=patterns,
        extra_patterns=list(modules.get("extra_patterns") or []),
        extra_excludes=list(modules.get("extra_excludes") or []),
        send_code_to_llm=bool(data.get("send_code_to_llm", False)),
        min_files_for_arch=int(data.get("min_files_for_arch", 3)),
        docs=docs_cfg,
    )


def _parse_docs_cfg(raw: object) -> DocsCfg:
    """Parse the optional ``docs:`` YAML block. Missing/None -> defaults.

    ``patterns: []`` is ambiguous with "use defaults" and would silently
    disable doc ingest — callers who want that should set ``enabled:
    false`` instead. So we surface an explicit error."""
    if raw is None:
        return DocsCfg()
    if not isinstance(raw, dict):
        raise ConfigError("code-index.yaml 'docs' block must be a mapping")
    patterns_raw = raw.get("patterns")
    if patterns_raw is not None and not isinstance(patterns_raw, list):
        raise ConfigError("docs.patterns must be a list")
    if isinstance(patterns_raw, list) and len(patterns_raw) == 0:
        raise ConfigError(
            "docs.patterns is empty; set enabled: false to disable docs "
            "indexing, or add at least one pattern"
        )
    excludes_raw = raw.get("extra_excludes")
    if excludes_raw is not None and not isinstance(excludes_raw, list):
        raise ConfigError("docs.extra_excludes must be a list")
    return DocsCfg(
        enabled=bool(raw.get("enabled", True)),
        patterns=(
            list(patterns_raw) if patterns_raw is not None
            else list(DEFAULT_DOC_PATTERNS)
        ),
        extra_excludes=list(excludes_raw or []),
        chunk_max_chars=int(raw.get("chunk_max_chars", 2000)),
        chunk_overlap_chars=int(raw.get("chunk_overlap_chars", 200)),
    )


def _detect_workspaces(root: pathlib.Path) -> list[str] | None:
    pj = root / "package.json"
    if not pj.exists():
        return None
    try:
        data = json.loads(pj.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    ws = data.get("workspaces")
    if isinstance(ws, dict):
        ws = ws.get("packages", [])
    if not isinstance(ws, list):
        return None
    return [w for w in ws if isinstance(w, str)]


def _detect_pnpm(root: pathlib.Path) -> list[str] | None:
    p = root / "pnpm-workspace.yaml"
    if not p.exists():
        return None
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        return None
    pkgs = data.get("packages") or []
    return pkgs if isinstance(pkgs, list) else None


def _detect_go_work(root: pathlib.Path) -> list[str] | None:
    p = root / "go.work"
    if not p.exists():
        return None
    uses: list[str] = []
    in_block = False
    for raw in p.read_text().splitlines():
        s = raw.strip()
        if s.startswith("use ("):
            in_block = True
            continue
        if in_block:
            if s == ")":
                in_block = False
                continue
            if s and not s.startswith("//"):
                s = s.split("//", 1)[0].strip()
                uses.append(s)
        elif s.startswith("use "):
            val = s[4:].strip().split("//", 1)[0].strip()
            uses.append(val)
    return uses or None


def _detect_cargo(root: pathlib.Path) -> list[str] | None:
    p = root / "Cargo.toml"
    if not p.exists():
        return None
    try:
        import tomllib
        data = tomllib.loads(p.read_text())
    except Exception:
        return None
    members = ((data.get("workspace") or {}).get("members")) or []
    return list(members) if isinstance(members, list) else None


def _detect_pants(root: pathlib.Path) -> list[str] | None:
    p = root / "pants.toml"
    if not p.exists():
        return None
    try:
        import tomllib
        data = tomllib.loads(p.read_text())
    except Exception:
        return None
    roots = (data.get("source", {}) or {}).get("root_patterns") or []
    globs: list[str] = []
    for r in roots:
        r = r.lstrip("/")
        if not r:
            continue
        globs.append(f"{r}/*")
    return globs or None


def _excluded(rel_path: str, patterns: list[str]) -> bool:
    p = pathlib.PurePosixPath(rel_path)
    for pat in patterns:
        try:
            if p.match(pat):
                return True
        except ValueError:
            pass
        if "/" in pat.strip("*").strip("/"):
            continue
        segment = pat.strip("*").strip("/")
        if segment and segment in p.parts:
            return True
    return False


def _expand_globs(root: pathlib.Path, patterns: list[str], excludes: list[str]) -> list[Module]:
    out: list[Module] = []
    seen: set[str] = set()
    for pat in patterns:
        for match in glob.iglob(str(root / pat), recursive=True):
            mp = pathlib.Path(match)
            if not mp.is_dir():
                continue
            rel = str(mp.relative_to(root))
            if rel in seen:
                continue
            if _excluded(rel, excludes):
                continue
            seen.add(rel)
            out.append(Module(name=rel, path=str(mp)))
    return sorted(out, key=lambda m: m.name)


def enumerate_files(module: Module, extra_excludes: list[str]) -> list[str]:
    excludes = DEFAULT_EXCLUDES + list(extra_excludes)
    root = pathlib.Path(module.path)
    out: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for fname in filenames:
            p = pathlib.Path(dirpath) / fname
            if p.is_symlink():
                continue
            rel = str(p.relative_to(root))
            if _excluded(rel, excludes):
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            out.append(str(p))
    return sorted(out)


def detect_language_mix(files: list[str]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for f in files:
        suffix = pathlib.Path(f).suffix
        if not suffix:
            continue
        ext = suffix.lstrip(".").lower()
        mix[ext] = mix.get(ext, 0) + 1
    return mix


def is_sym_capable(mix: dict[str, int]) -> bool:
    total = sum(mix.values())
    if total == 0:
        return False
    serena_count = sum(n for ext, n in mix.items() if ext in SERENA_EXTS)
    return (serena_count / total) > 0.5


def discover_modules(cfg: Config) -> list[Module]:
    root = pathlib.Path(cfg.repo_root)
    excludes = cfg.excludes
    if cfg.discovery_mode == "patterns":
        return _expand_globs(root, cfg.patterns + cfg.extra_patterns, excludes)
    for detector in (
        _detect_workspaces, _detect_pnpm, _detect_go_work, _detect_cargo, _detect_pants,
    ):
        pats = detector(root)
        if pats:
            return _expand_globs(root, pats + cfg.extra_patterns, excludes)
    raise ConfigError("no recognized manifest for 'from: auto' (add explicit patterns)")
