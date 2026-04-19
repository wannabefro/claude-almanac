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
    name: str                                # "ollama", "openai", "voyage" — the PROVIDER string
    dim: int
    distance: Literal["l2", "cosine"]
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**`Embedder.name` is the provider string, not the model.** The model is a separate field on the adapter and stored per-DB in the `meta` table. Archive/code-index/activity DBs store `(provider, model, dim, distance)` tuples and reject reads when they mismatch (`EmbedderMismatch` exception). Never "auto-migrate" on mismatch — fail loudly so the user re-indexes intentionally.

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
- `paths.global_memory_dir()` / `paths.project_memory_dir(cwd)` — scoped memory dirs. Project key is sha256 of the parent of `git-common-dir` (so worktrees share state).

Override the data dir for tests or re-homing via `CLAUDE_ALMANAC_DATA_DIR`. Override config via `CLAUDE_ALMANAC_CONFIG_DIR`. Tests use `monkeypatch.setenv` on these; see `tests/unit/test_paths.py` for the pattern.

## Module map

| Area | Location |
|---|---|
| Archive DB + schema | `src/claude_almanac/core/archive.py` |
| Retrieve / inject | `src/claude_almanac/core/retrieve.py` |
| Curator (Stop hook) | `src/claude_almanac/core/curator.py` + `core/assets/curator-prompt.md` |
| Paths (XDG) | `src/claude_almanac/core/paths.py` |
| Config | `src/claude_almanac/core/config.py` |
| Embedder adapters | `src/claude_almanac/embedders/{ollama,openai,voyage}.py` + `profiles.py` |
| Code index (sym pass) | `src/claude_almanac/codeindex/sym.py` |
| Code index (arch pass) | `src/claude_almanac/codeindex/arch.py` — TRUST BOUNDARY |
| Auto-inject gate | `src/claude_almanac/codeindex/autoinject.py` |
| Digest generator | `src/claude_almanac/digest/generator.py` |
| Digest server + routes | `src/claude_almanac/digest/server.py` |
| Q&A tools | `src/claude_almanac/digest/qa/tools/` |
| Platform (launchd/systemd) | `src/claude_almanac/platform/{macos_launchd,linux_systemd}.py` |
| Hook entrypoints | `src/claude_almanac/hooks/{retrieve,curate}.py` |
| CLI | `src/claude_almanac/cli/` |

## Files never to edit directly

- `src/claude_almanac/platform/templates/**/*.j2` — Jinja templates for launchd/systemd units. Edit cautiously and regenerate golden files under `tests/unit/golden/platform/` via `pytest --snapshot-update` or manual regen; never hand-edit the goldens.
- `tests/unit/golden/**` — generated by snapshot tests. Regenerate via the tests themselves, don't hand-edit.
- `CHANGELOG.md` release sections — append only in `## [Unreleased]` during development; the release task moves entries into a versioned section.
- `plugin.json` `version` — changed only by the release flow (Task 15), kept in lockstep with `pyproject.toml::version`.
- `src/claude_almanac/embedders/profiles.py` — add new entries, but never hand-tune existing `dedup_distance` values. Thresholds come from the calibration harness (`claude-almanac calibrate`) and must be reproducible.

## Lint + typecheck

```bash
ruff check .                                  # lint
ruff check . --fix                            # autofix where safe
mypy src/claude_almanac                       # typecheck (strict on src/, looser on tests/)
```

CI enforces ruff + mypy on every PR. Run locally before committing; the project-local `.claude/verify-on-edit` hook also runs syntax validation on save.

## Self-review before PR

Before opening a PR or running `/commit`:

1. Re-read the diff and check for scope drift (did I do only what I set out to do?).
2. Run `pytest tests/unit -v` and ensure green.
3. Run `ruff check .` and `mypy src/claude_almanac`; both must be clean.
4. If the diff touches `codeindex/arch.py`, `core/retrieve.py`, or `codeindex/dispatch.py`, invoke the `trust-boundary-reviewer` agent (see `.claude/agents/`).
5. For meaningful behavioral changes, invoke the global `reviewer` agent at the task boundary.
6. Commit message names the *why*, not the *what*. Small, focused commits.
