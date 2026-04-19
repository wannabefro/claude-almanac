# claude-almanac — Contributor guidance for Claude Code

This file is read by Claude Code when working inside the claude-almanac repository. It captures invariants and commands that aren't obvious from the file tree. User-facing docs live under `docs/`; this file is for the *contributor* session.

## Project overview

claude-almanac is a Claude Code plugin + installable Python package providing three subsystems: self-curating memory (archive DB + markdown files, per-repo and global), daily digest (per-repo commit summaries + local Q&A server), and per-repo code index (symbol-level vector search + optional LLM-powered arch summaries). All three share one pluggable embedder, one XDG-compliant data dir, and platform adapters for macOS (launchd) and Linux (systemd). See [docs/architecture.md](docs/architecture.md) for the system map.

## Running tests

```bash
source .venv/bin/activate && pytest tests/unit -v     # unit only (fast, default)
pytest -m integration -v                              # integration (requires live Ollama + bge-m3)
pytest tests/ -v                                      # both
pytest tests/unit --cov=src/claude_almanac --cov-report=term-missing  # with coverage
```

Always activate the venv first. Integration tests are skipped by default via `addopts = "-m 'not integration'"` in `pyproject.toml`; pass `-m integration` explicitly to run them.

## TDD expectation

- For any branching logic with calibrated thresholds (dedup, arch trust gate, auto-inject gate), **write the failing test first**, then the implementation. Red → green → refactor.
- For pure plumbing (I/O, subprocess, template rendering), implementation + mock-based unit test in the same commit is fine.
- Commits are small and focused: one behavioral change per commit. A test-adding commit that goes red is fine; an implementation-only commit with no accompanying test is not.

## Embedder contract

`src/claude_almanac/embedders/base.py` defines the `Embedder` protocol:

```python
class Embedder(Protocol):
    name: str                                # "ollama" | "openai" | "voyage" — the PROVIDER string
    model: str                               # "bge-m3", "text-embedding-3-small", etc.
    dim: int
    distance: Literal["l2", "cosine"]
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**`Embedder.name` is the provider string, not the model.** `Embedder.model` carries the model identifier. Both are stored per-DB in the `meta` table. Archive/code-index/activity DBs store `(provider, model, dim, distance)` tuples and reject reads when they mismatch (`EmbedderMismatch` exception). Never "auto-migrate" on mismatch — fail loudly so the user re-indexes intentionally.

**Per-provider dedup thresholds** live in `src/claude_almanac/embedders/profiles.py`. They're not universal: `l2` distances for `bge-m3` (unnormalized) land in the ~14-29 range; cosine distances for OpenAI/Voyage land in 0-1. Never copy a threshold across providers. When adding a new adapter, run the calibration helper (`python -m claude_almanac.embedders.calibrate <fixture-dir>`) and commit the derived threshold with the fixture.

## Trust boundary — code-index `arch` pass

`src/claude_almanac/codeindex/arch.py` runs the LLM-powered module summary pass, which **sends source content to Anthropic via the `claude` CLI**. This is gated by a **dual `send_code_to_llm: true` flag** — BOTH the repo-local `.claude/code-index.yaml` AND the global `~/.config/claude-almanac/config.yaml` must opt in. Default is `false` in both scopes.

Never weaken this gate. If you're editing `arch.py`, `core/retrieve.py` (the auto-inject code path), or `codeindex/dispatch.py`:

1. Re-read `arch.py::_should_run` (or equivalent). Both flags must be checked; a single-flag shortcut is a regression.
2. The `sym` pass (symbol-signature embeddings) never sends source — don't accidentally wire arch gating into sym, or sym into arch.
3. When in doubt, invoke the `trust-boundary-check` skill in `.claude/skills/` and have the `trust-boundary-reviewer` agent review the diff before commit.

## Path resolution

All persistent paths go through `src/claude_almanac/core/paths.py`. Never hard-code paths; use the helpers:

- `paths.data_dir()` — base XDG data dir (`~/Library/Application Support/claude-almanac` on macOS, `$XDG_DATA_HOME/claude-almanac` on Linux).
- `paths.config_dir()` — config dir.
- `paths.global_memory_dir()` / `paths.project_memory_dir()` — scoped memory dirs. Both take no arguments. The project key is `sha256(parent of git-common-dir)` (via `paths.project_key()`) so worktrees share state. When not in a git repo, falls back to a `cwd-<hash>` key.

Override the data dir for tests or re-homing via `CLAUDE_ALMANAC_DATA_DIR`. Override config via `CLAUDE_ALMANAC_CONFIG_DIR`. Tests use `monkeypatch.setenv` on these; see `tests/unit/test_paths.py` for the pattern.

## Module map

| Area | Location |
|---|---|
| Archive DB + schema | `src/claude_almanac/core/archive.py` |
| Dedup pre-check (the 17.0 threshold contract) | `src/claude_almanac/core/dedup.py` |
| Retrieve / inject (UserPromptSubmit hook) | `src/claude_almanac/core/retrieve.py` |
| Curator (Stop hook) | `src/claude_almanac/core/curator.py` + `core/assets/curator-prompt.md` |
| Paths (XDG) | `src/claude_almanac/core/paths.py` |
| Config | `src/claude_almanac/core/config.py` |
| Embedder adapters | `src/claude_almanac/embedders/{ollama,openai,voyage}.py` + `profiles.py` + `calibrate.py` |
| Code index (DB) | `src/claude_almanac/codeindex/db.py` |
| Code index (sym pass, extract + embed + upsert) | `src/claude_almanac/codeindex/sym.py` |
| Code index (arch pass, LLM module summaries) | `src/claude_almanac/codeindex/arch.py` — **TRUST BOUNDARY** |
| Code index (extractor dispatch) | `src/claude_almanac/codeindex/extractors/dispatch.py` |
| Extractors | `src/claude_almanac/codeindex/extractors/{python_ast,regex_tuned,serena_fallback}.py` |
| Auto-inject gate | `src/claude_almanac/codeindex/autoinject.py` |
| Digest generator pipeline | `src/claude_almanac/digest/generator.py` |
| Digest activity DB | `src/claude_almanac/digest/activity_db.py` |
| Digest collectors (memory/retrievals/git) | `src/claude_almanac/digest/collectors.py` |
| Digest render (Haiku narratives) | `src/claude_almanac/digest/render.py` |
| Digest FastAPI server + routes | `src/claude_almanac/digest/server.py` + `digest/templates/` + `digest/static/` |
| Q&A registry + fast/deep modes | `src/claude_almanac/digest/qa/{registry,fast,deep,api}.py` |
| Q&A built-in tools | `src/claude_almanac/digest/qa/tools/{search_activity,git_show}.py` |
| Platform (launchd/systemd) | `src/claude_almanac/platform/{macos_launchd,linux_systemd}.py` + `platform/templates/` |
| Hook entrypoints | `src/claude_almanac/hooks/{retrieve,curate}.py` |
| CLI dispatch + subcommands | `src/claude_almanac/cli/{main,setup,recall,digest,codeindex}.py` |
| Slash commands (ship with plugin) | `commands/{recall,digest,almanac}.md` |
| User-facing skills (ship with plugin) | `skills/{recall,digest}/SKILL.md` |
| Contributor skills (this repo only) | `.claude/skills/{add-embedder,trust-boundary-check,test-conventions}/SKILL.md` |
| Contributor agents (this repo only) | `.claude/agents/{embedder-calibrator,trust-boundary-reviewer}.md` |

## Running things locally during dev

```bash
# Memory curator (Stop hook target) — normally forked by the Stop hook; invoke manually with a transcript to dry-run
CLAUDE_ALMANAC_TRANSCRIPT=/path/to/session.jsonl python -m claude_almanac.core.curator

# Digest generator — writes today's digest markdown + updates activity.db
claude-almanac digest generate
claude-almanac digest generate --date 2026-04-19 --repo myrepo

# Digest web UI — FastAPI on 127.0.0.1:8787
uvicorn claude_almanac.digest.server:app --host 127.0.0.1 --port 8787
# or once setup has run:
claude-almanac digest serve

# Code index ops on current repo
claude-almanac codeindex init
claude-almanac codeindex refresh
claude-almanac codeindex status

# Recall memory
claude-almanac recall search "your query"
claude-almanac recall code "verify_token"     # symbol-level search
```

## Files never to edit directly

- `src/claude_almanac/platform/templates/**/*.j2` — Jinja templates for launchd/systemd units. The unit tests render them and assert key fragments; preserve the variable names Jinja references (`unit_name`, `command`, `hour`, etc.).
- `src/claude_almanac/digest/templates/**/*.html` and `digest/static/app.css` — the web UI's visual layer was produced via the `frontend-design` skill with a deliberate aesthetic. If the UI needs polish, re-invoke `frontend-design`; don't hand-roll CSS.
- `plugin.json` `version` — changed only by the release flow (Task 15 in the polish plan), kept in lockstep with `pyproject.toml::version`.
- `src/claude_almanac/embedders/profiles.py` — add new `EmbedderProfile` entries for new providers, but never hand-tune existing `dedup_distance` values. Thresholds come from running `python -m claude_almanac.embedders.calibrate` against a calibration fixture and must be reproducible.

## Lint + typecheck

```bash
ruff check .                                  # lint
ruff check . --fix                            # autofix where safe
mypy src/claude_almanac                       # typecheck (strict on src/, looser on tests/)
```

CI enforces ruff + mypy on every PR (see `.github/workflows/ci.yml`). Run locally before committing.

## Self-review before PR

Before opening a PR or running `/commit`:

1. Re-read the diff and check for scope drift (did I do only what I set out to do?).
2. Run `pytest tests/unit -v` and ensure green.
3. Run `ruff check .` and `mypy src/claude_almanac`; both must be clean.
4. If the diff touches `codeindex/arch.py`, `core/retrieve.py`, `codeindex/autoinject.py`, or `codeindex/extractors/dispatch.py`, invoke the `trust-boundary-reviewer` agent (see `.claude/agents/`).
5. For meaningful behavioral changes, invoke a `reviewer` at the task boundary — self-critique ~10s first to filter trivia.
6. Commit message names the *why*, not the *what*. Small, focused commits.

## Key invariants (summary)

- **Embedder mismatch → EmbedderMismatch**, never silent re-embed.
- **Arch pass requires BOTH `send_code_to_llm` flags** (global + per-repo). Default is False for both.
- **Curator runs in a background process** (forked by Stop hook); never block the hook.
- **XDG paths only**, overridable via env. No `~/` literals, no `/tmp` literals outside tests.
- **Plan 1's test suite (69 tests) must keep passing** after any Plan 2/3/4 change — it's the foundation contract.
