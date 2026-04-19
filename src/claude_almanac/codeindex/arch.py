"""Module-level architecture summarization via the Anthropic CLI.

Trust boundary: This module sends source-file content to Anthropic. It
refuses to run unless BOTH the repo-local code-index.yaml and the global
config.yaml opt in via send_code_to_llm: true. Default in both scopes is
False (spec invariant).

Prompt template: src/claude_almanac/codeindex/assets/arch_prompt.md.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time
from importlib.resources import files

# See init.py for DEVELOPER_DIR rationale.
os.environ.pop("DEVELOPER_DIR", None)

from . import config as _cfg
from . import db as _db
from .log import emit
from ..core import paths
from ..embedders import make_embedder as _make_embedder  # re-exported for tests to patch

_ENTRYPOINTS = (
    "main.tf", "variables.tf", "outputs.tf", "terragrunt.hcl",
    "index.ts", "index.tsx", "index.js", "main.ts",
    "main.py", "__init__.py", "manage.py",
    "main.go", "cmd.go",
    "Chart.yaml", "values.yaml",
)
MAX_FILES_PER_ARCH = 20
MAX_FILE_BYTES_IN_PROMPT = 4096
ARCH_DEDUP_THRESHOLD = float(os.environ.get("CLAUDE_ALMANAC_ARCH_DEDUP", "17.0"))


def _load_prompt_template() -> str:
    return (files("claude_almanac.codeindex") / "assets" / "arch_prompt.md").read_text()


def select_files(files_: list[str], cap: int = MAX_FILES_PER_ARCH) -> list[str]:
    # Two-tier key: bucket 0 = entrypoints (ordered by _ENTRYPOINTS index);
    # bucket 1 = everything else (largest first). Entrypoints always precede
    # non-entrypoints regardless of size.
    entries: list[tuple[tuple[int, int], str]] = []
    for f in files_:
        name = pathlib.Path(f).name
        try:
            size = pathlib.Path(f).stat().st_size
        except OSError:
            continue
        if name in _ENTRYPOINTS:
            key = (0, _ENTRYPOINTS.index(name))
        else:
            key = (1, -size)
        entries.append((key, f))
    entries.sort(key=lambda e: e[0])
    return [e[1] for e in entries[:cap]]


def _build_prompt(module_name: str, files_: list[str], repo_root: str,
                  language_mix: dict[str, int]) -> str:
    tpl = _load_prompt_template()
    blocks: list[str] = []
    for f in files_:
        rel = str(pathlib.Path(f).relative_to(repo_root))
        try:
            body = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES_IN_PROMPT]
        except OSError:
            continue
        blocks.append(f"=== {rel} ===\n{body}\n")
    return (tpl
            .replace("{module_name}", module_name)
            .replace("{language_mix}", json.dumps(language_mix))
            .replace("{file_sections}", "\n".join(blocks)))


def _haiku(prompt: str) -> str:
    res = subprocess.run(
        ["claude", "-p", "--model", "haiku"],
        input=prompt, capture_output=True, text=True, check=True, timeout=90,
    )
    return res.stdout.strip()


def _git_target_sha(repo_root: str, default_branch: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"origin/{default_branch}"],
        cwd=repo_root, text=True,
    ).strip()


def _ci_db_path() -> pathlib.Path:
    p = paths.project_memory_dir() / "code-index.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_one(*, db_path: str, repo_root: str, module_name: str,
            files_: list[str], language_mix: dict[str, int], commit_sha: str,
            embedder: object,
            send_code_to_llm: bool, global_send_code_to_llm: bool) -> bool:
    log_path = paths.logs_dir() / "code-index.log"
    # Trust-boundary gate: refuse here so any direct caller (CLI, future
    # wiring) hits the same check that main() enforces. Both repo-local and
    # global must opt in.
    if not send_code_to_llm or not global_send_code_to_llm:
        emit(log_path, component="code-index", level="warn", event="arch.refused",
             module=module_name, reason="send_code_to_llm gate")
        return False
    selected = select_files(files_)
    if not selected:
        emit(log_path, component="code-index", level="info", event="arch.skip",
             module=module_name, reason="no_files")
        return True
    t0 = time.time()
    prompt = _build_prompt(module_name, selected, repo_root, language_mix)
    try:
        summary = _haiku(prompt)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        emit(log_path, component="code-index", level="error", event="arch.haiku_fail",
             module=module_name, err=str(e))
        return False
    if not summary:
        emit(log_path, component="code-index", level="warn", event="arch.empty_summary",
             module=module_name)
        return False
    try:
        [vec] = embedder.embed([summary])  # type: ignore[attr-defined]
    except Exception as e:
        emit(log_path, component="code-index", level="error", event="arch.embed_fail",
             module=module_name, err=str(e))
        return False
    existing = _db.nearest(db_path, embedding=vec, kind="arch")
    if existing and existing["distance"] < ARCH_DEDUP_THRESHOLD:
        emit(log_path, component="code-index", level="info", event="arch.dedup_skip",
             module=module_name, distance=f'{existing["distance"]:.3f}')
        return True
    _db.upsert_sym(db_path, kind="arch", text=summary, file_path=None,
                   symbol_name=None, module=module_name,
                   line_start=None, line_end=None,
                   commit_sha=commit_sha, embedding=vec)
    emit(log_path, component="code-index", level="info", event="arch.upsert",
         module=module_name, dur_ms=int((time.time() - t0) * 1000))
    return True


def main(repo_root: str, *, global_send_code_to_llm: bool) -> int:
    repo_root = str(pathlib.Path(repo_root).resolve())
    c = _cfg.load(repo_root)
    if not c.send_code_to_llm or not global_send_code_to_llm:
        print("send_code_to_llm: false — skipping arch pass "
              "(requires BOTH repo-local and global opt-in)")
        return 0
    dbp = _ci_db_path()
    if not dbp.exists():
        print("no code-index.db — run `claude-almanac codeindex init` first")
        return 1
    dirty = _db.list_dirty(str(dbp))
    if not dirty:
        print("no dirty modules")
        return 0
    mods_by_name = {m.name: m for m in _cfg.discover_modules(c)}
    target_sha = _git_target_sha(repo_root, c.default_branch)
    # Embedder: global config → make_embedder. Import lazily so tests can patch.
    from ..core import config as _app_config
    app_cfg = _app_config.load()
    embedder = _make_embedder(app_cfg.embedder.provider, app_cfg.embedder.model)
    done = 0
    for module_name, _sha in dirty:
        m = mods_by_name.get(module_name)
        if m is None:
            _db.clear_dirty(str(dbp), module_name)
            continue
        files_ = _cfg.enumerate_files(m, c.extra_excludes)
        if len(files_) < c.min_files_for_arch:
            _db.clear_dirty(str(dbp), module_name)
            continue
        mix = _cfg.detect_language_mix(files_)
        ok = run_one(db_path=str(dbp), repo_root=repo_root, module_name=module_name,
                     files_=files_, language_mix=mix, commit_sha=target_sha,
                     embedder=embedder,
                     send_code_to_llm=c.send_code_to_llm,
                     global_send_code_to_llm=global_send_code_to_llm)
        if ok:
            _db.clear_dirty(str(dbp), module_name)
            done += 1
    print(f"arch complete: {done}/{len(dirty)} modules summarized")
    return 0
