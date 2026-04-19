# Changelog

All notable changes to claude-almanac will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] — 2026-04-19

### Fixed

- Plugin's `hooks/hooks.json` used a bare `python -m claude_almanac.hooks.*` command that could not resolve the package when the CLI was installed via `uv tool install` (isolated venv) or `pipx`. Hooks would fail silently with `ModuleNotFoundError`.
- New console-script entry points ship with the package: `claude-almanac-retrieve-hook` and `claude-almanac-curate-hook`. The plugin's `hooks/hooks.json` now invokes these by name, so any installer (`uv tool install`, `pipx`, `pip install --user`, plain `pip`) puts them on PATH and hooks work out of the box.
- Version consistency enforced across `pyproject.toml`, `plugin.json`, and `.claude-plugin/marketplace.json`.

## [0.1.0] — 2026-04-19

Initial public release. A daily intelligence layer for Claude Code: self-curating memory, per-repo code-symbol index, and daily digest with Q&A, all installable as a single Claude Code plugin.

### Added

#### Memory subsystem
- `UserPromptSubmit` hook that auto-injects relevant memories from global + current-project archives.
- `Stop` hook that forks a background curator worker (Haiku-powered) to decide what's worth saving from the just-finished session.
- Semantic dedup pre-check with a calibrated 17.0 L2-distance threshold for Ollama `bge-m3` (empirically tuned against real archive workload; duplicate ceiling ~16, same-topic floor ~21).
- `/recall` slash command with `search`, `search-all`, `list`, `show` subcommands. `pin`, `unpin`, `forget`, `export` deferred to v0.2 with clearer stub messaging.
- `sqlite-vec` archive DB with per-DB embedder metadata guard (`EmbedderMismatch` raised on mismatch; never silent re-embed).
- Transcript JSONL parser: curator reads the session transcript path passed via `CLAUDE_ALMANAC_HOOK_TRANSCRIPT` env var.

#### Code-index subsystem
- Per-repo symbol index (`sym` pass): Python AST extractor, regex-tuned extractor for TS/JSX/Go/Java, Serena HTTP fallback for Rust and other languages.
- LLM-powered module architecture summaries (`arch` pass), gated behind a **dual `send_code_to_llm`** flag (global config AND per-repo `.claude/code-index.yaml` must both opt in; default is `false` in both scopes).
- Auto-inject gate that surfaces matching code symbols alongside memory hits when the user's prompt looks code-ish.
- `claude-almanac codeindex {init,refresh,status,arch}` CLI for first-time indexing, incremental updates, DB health checks, and on-demand arch passes.
- `claude-almanac recall code <query>` for direct symbol-level retrieval.
- Workspace discovery modes: auto, pnpm-workspaces, Pants `source_roots`, Go workspaces, Cargo workspaces; explicit patterns fallback.

#### Digest subsystem
- Daily digest generator: collects 24h memory activity, retrieval usage, and git commits across configured repos; embeds commits into `activity.db` (sqlite-vec, same embedder as the memory archive); renders markdown via Haiku.
- FastAPI web UI on `127.0.0.1:8787`: home page, digest history, per-repo digest pages, synchronous `/ask` and streaming `/ask/stream` (SSE) Q&A, on-demand `/generate` form.
- Q&A engine with fast mode (single `search_activity` + Haiku synthesize) and deep mode (multi-tool loop via `claude-agent-sdk` MCP server, with `search_activity` and `git_show` tools).
- Plugin-style tool registry: forks can register their own Q&A tools via a `@tool` decorator and module auto-discovery.
- `claude-almanac digest {generate,serve}` CLI.
- `/digest` slash command with `today`, `<date>`, and `generate` dispatch.

#### Pluggable embedders
- `Embedder` protocol with `name` (provider), `model`, `dim`, `distance` fields.
- Adapters: Ollama (`bge-m3`, default, local, no API key), OpenAI (`text-embedding-3-small`, `[openai]` extra), Voyage (`voyage-3-large`, `[voyage]` extra).
- Per-embedder calibrated `dedup_distance` profiles in `embedders/profiles.py`; calibration helper at `python -m claude_almanac.embedders.calibrate`.

#### Platform + install
- macOS: launchd plist templates for digest generator (daily) and server (always-on); `terminal-notifier` with `osascript` fallback.
- Linux: systemd user unit + timer templates; `notify-send` with no-op fallback.
- XDG-compliant storage: `~/Library/Application Support/claude-almanac` on macOS, `$XDG_DATA_HOME/claude-almanac` on Linux. Overridable via `CLAUDE_ALMANAC_DATA_DIR` / `CLAUDE_ALMANAC_CONFIG_DIR`.
- `claude-almanac setup` installs deps, writes default `config.yaml`, renders platform units when digest is enabled, probes the configured embedder for reachability.
- `claude-almanac setup --uninstall` / `--purge-data` for clean reversal.

#### Plugin integration
- Plugin manifest (`plugin.json`) with marketplace metadata (keywords, repository, license, author, homepage).
- Slash commands: `/recall`, `/digest`, `/almanac`.
- Bundled skills: `skills/recall/SKILL.md` and `skills/digest/SKILL.md` teach Claude when to invoke the commands proactively (past-context questions, activity-shaped questions).
- Bash wrapper at `bin/recall` for the `/recall` slash command.

#### Developer experience
- Repo-local `CLAUDE.md` with contributor guidance (test commands, TDD expectation, embedder contract, trust boundary, XDG paths, module map, lint + typecheck, self-review checklist, key invariants).
- Contributor skills: `.claude/skills/{add-embedder,trust-boundary-check,test-conventions}/SKILL.md`.
- Contributor agents: `.claude/agents/{embedder-calibrator,trust-boundary-reviewer}.md`.
- GitHub Actions CI: macOS + Ubuntu × Python 3.11 + 3.12 matrix running ruff + mypy + unit tests; live-Ollama integration job gated on `main` pushes.
- Release workflow (`.github/workflows/release.yml`): on `v*` tags, builds with `python -m build`, verifies version consistency between `pyproject.toml` and `plugin.json`, publishes to PyPI via trusted publisher, creates a GitHub release with dist attachments.

### Known limitations

- Ollama + `bge-m3` is the only pre-calibrated embedder profile; OpenAI and Voyage ship with provisional thresholds that should be tuned via the calibration harness before relying on dedup behavior with them.
- Windows is not supported (macOS + Linux only in v0.1).
- `conv` code-index extractor (LLM-extracted convention summaries) is intentionally deferred — see `code_indexing_design_risks` memo for rationale.
- Recall `pin`, `unpin`, `forget`, `export` subcommands are stubbed with a "deferred to v0.2" message.
- Daemon install for nightly code-index refresh is manual (scheduler hooks exist but aren't wired into `setup`).

### Security

- `arch` pass sends source content to Anthropic via the local `claude` CLI. The dual `send_code_to_llm` flag (global + per-repo, both default `false`) means this is strictly opt-in.
- All other subsystems (memory curation, digest generation, Q&A) send conversation text or commit metadata only — never raw source files — unless the arch gate is explicitly enabled.
- No telemetry, no API keys stored, no cloud defaults. Ollama is the out-of-the-box embedder.

[Unreleased]: https://github.com/wannabefro/claude-almanac/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/wannabefro/claude-almanac/releases/tag/v0.1.0
