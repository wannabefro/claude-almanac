# Changelog

All notable changes to claude-almanac will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-04-20 — Curator provider switch (v0.3 §3.0)

### Added

- **`curators/` package** — pluggable curator LLM provider layer mirroring `embedders/`. `Curator` Protocol (`name`, `model`, `timeout_s: float`, `invoke(system_prompt, user_turn) -> str`), a `make_curator(cfg)` dispatch factory, and two shipped providers:
  - `OllamaCurator` — calls `/api/chat` with `format: "json"` and `temperature: 0`. Default model `gemma3:4b`.
  - `AnthropicCurator` — calls the official `anthropic` SDK's `messages.create` directly with `ANTHROPIC_API_KEY`. Default model `claude-haiku-4-5-20251001`.
- **`CuratorCfg`** in `core.config` — new `curator:` YAML block with `provider`, `model`, `timeout_s` fields. Defaults to `ollama` / `gemma3:4b`. Old `0.2.x` configs load cleanly with the defaults backfilled on first save.
- **Automatic migration in `claude-almanac setup`.** On first run against a config that lacks a `curator:` block, setup picks the right provider based on `ANTHROPIC_API_KEY` in env: present → `anthropic_sdk` + Haiku, absent → `ollama` + `gemma3:4b` plus `ollama pull gemma3:4b` when reachable. Pre-existing `curator:` blocks are respected; only `provider=ollama` configs get a re-pull on subsequent runs to self-heal after upgrades.
- **`/almanac status` curator section** — shows `provider (model)` and `last invocation: <ts>` derived from `curator.log` mtime.
- **Integration parity suite** — `tests/integration/test_curator_providers.py` runs both providers against four real-session fixtures (`chatty_output`, `pure_chatter`, `durable_memory_signal`, `large_180kb`). Asserts shape (every decision has a known action; `write_md`/`update_md` carry name + content) plus two behavioral guards: the durable-signal fixture must emit a non-skip decision on both providers; the pure-chatter fixture must never emit a write. Gated behind `@pytest.mark.integration`.
- **CI improvements** — `.github/workflows/ci.yml` integration job switched from the `services:` block to explicit `docker run -v /tmp/ollama-models:/root/.ollama`. `actions/cache@v4` persists the models dir across runs (key `ollama-models-v1-bge-m3-gemma3-4b`). Adds `gemma3:4b` pull step alongside `bge-m3`. Wires the new `ANTHROPIC_API_KEY` repo secret into the pytest env so the Anthropic provider runs end-to-end.
- **Test-isolation guard for `codeindex` unit tests** — new `tests/unit/codeindex/conftest.py` autouse fixture pins `CLAUDE_ALMANAC_DATA_DIR` and `CLAUDE_ALMANAC_CONFIG_DIR` to `tmp_path` for every test in the subpackage. Prior to this fix, `test_arch.py` and `test_sym.py` wrote synthetic log lines (`module=m err=boom symbol=pub sha=sha1`) into the real XDG log on every `pytest` run, accumulating ~83 MB of noise.

### Changed

- **BREAKING: the `claude -p --model haiku` subprocess curator path is removed.** `core/curator.py::_run_llm` now delegates to `make_curator(cfg).invoke(...)`. The 30–45 s CLI boot on every Stop hook is gone; real curator invocations complete in under 5 s end-to-end (Ollama warm: ~1 s model, ~4 s embedder + archive writes).
- **`anthropic>=0.40,<1.0`** added as a core dependency. Intentional — the fast-API path requires the SDK to be importable regardless of the user's chosen provider.
- **`CURATOR_TIMEOUT_S` module constant removed.** Timeouts are per-provider now (`_DEFAULT_TIMEOUT = {"ollama": 30, "anthropic_sdk": 15}`), configurable via `curator.timeout_s` in `config.yaml`.
- **Curator prompt output format** — the template now asks for `{"decisions": [...]}` rather than a bare `[...]` array. Ollama's `format: "json"` constrains output to a JSON object; the old prompt caused gemma3:4b to return `{}` and silently drop every transcript. The existing `_parse_decisions` helper already tolerated this shape, so Haiku behavior is unchanged.

### Fixed

- **Ollama curator error handling** widened from `(TimeoutException, ConnectError)` to the broader `httpx.RequestError`, covering `RemoteProtocolError` and other transient failures the sibling embedder pattern already handles. The bare `assert isinstance(content, str)` path was replaced with a logged warning + empty-string return to honor the Protocol's "providers never raise" contract.
- **Anthropic curator error handling** narrowed from `except Exception` to `except anthropic.APIError`, so non-SDK exceptions (`MemoryError`, bugs) propagate instead of being silently swallowed. All SDK-layer failures (connection, timeout, rate, auth, bad request) still yield an empty string.

### Deferred to 0.3.1+

- §3.1 Session-transcript compression
- §3.2 Temporal decay scoring
- §3.3 Knowledge-graph edges
- §3.4 Memory versioning

## [0.2.8] — 2026-04-20

### Fixed

- **Curator prompt never substituted its own placeholders.** `{{EXISTING_MEMORIES}}`, `{{USER_PROMPT}}`, and `{{ASSISTANT_RESPONSE}}` were emitted verbatim to Haiku because the only substitution site ever filled them. Haiku sometimes replied "no actual turn provided — curator template with unfilled `{{USER_PROMPT}}` and `{{ASSISTANT_RESPONSE}}` variables" and skipped the turn. Now: `{{USER_PROMPT}}` / `{{ASSISTANT_RESPONSE}}` are removed from the template (the transcript flows via stdin, not via prompt substitution), and `{{EXISTING_MEMORIES}}` is substituted with a summary of md files across the global + current-project scopes so Haiku can route refinements to `update_md` with the existing slug instead of coining near-duplicate names.
- **Timeout log dumped the full ~3KB system prompt** on every `TimeoutExpired` because `subprocess.TimeoutExpired.__str__` includes the cmd argv. Replaced the generic `%s` format with an explicit one-line message: `curator LLM call timed out after 60s`.
- **`FileNotFoundError` path** (when the `claude` CLI isn't on PATH) also logged the full exception; now logs `curator: \`claude\` CLI not on PATH`.

### Notes

- Keeping the curator timeout at 60s deliberately. Haiku's API call is sub-second; the 30–45s wall time users see is entirely the `claude` CLI booting (hooks, plugin sync, CLAUDE.md autoload, MCP init). Longer timeouts mask that overhead without fixing it. v0.3 plans to switch the curator to a local Ollama model (default `gemma3:4b`) to eliminate the CLI wrapper entirely — see ROADMAP.md §3.0.

## [0.2.7] — 2026-04-20

### Fixed

- **Curator auth broke on 0.2.6** for users on OAuth/keychain auth (the default). 0.2.6 added `--bare` to the curator's `claude` invocation thinking it would keep Haiku out of the host CLAUDE.md, but `--bare` forces strict `ANTHROPIC_API_KEY` / `apiKeyHelper` auth and skips keychain/OAuth. The curator began returning `Not logged in · Please run /login` to every Haiku call, dropping all memories. Drop `--bare`; `--system-prompt` alone carries the conversational-drift fix verified end-to-end: 4 runs against a chatty transcript produced 0 non-JSON warnings and exactly 1 archive row per scope with the rest correctly going to `skip_all`.

## [0.2.6] — 2026-04-20

### Fixed

- **Curator drifted into conversational replies** when the transcript contained chatty content. The curator prompt used to be piped to Haiku as the user turn (same channel as the transcript), so Haiku sometimes answered "I'm Claude Code, those curator instructions were pasted by mistake" and emitted no JSON. Now the prompt is passed via `--system-prompt` (Haiku's system role) and the transcript is stdin. Also pass `--bare` so Haiku doesn't auto-load the host project's CLAUDE.md / hooks / plugins and get further distracted. Expected effect: far fewer "LLM returned non-JSON" warnings and dropped turns.
- **Curator re-extracted memories piled up duplicate rows.** On every Stop hook firing, Haiku re-extracts the same durable memories from the growing transcript; with the dedup fix in 0.2.5 the redirect works correctly, but the worker still overwrote the md file and inserted a new archive row each time even when the proposed content was byte-identical to what was already on disk. Now when `target.exists() && target.read_text() == text`, the write + insert are skipped and the worker logs `skip identical re-write`. Paraphrase re-writes (different body, same slug after redirect) still overwrite and insert — that's a legitimate re-confirmation with improved phrasing.
- **Daemons stayed on the old Python venv after `uv tool upgrade`.** `launchctl`/`systemctl` don't auto-restart a service when its managed package is upgraded, so the digest server kept running under a venv whose `site-packages` predated template/endpoint changes, returning stale 500s until manual `launchctl kickstart -k`. The auto-upgrade runner now invokes `claude-almanac setup` after a successful `uv tool upgrade` — setup's idempotent unit install already does an unload/load cycle, so daemons come back up on the fresh venv automatically.

## [0.2.5] — 2026-04-20

### Fixed

- **Critical:** bge-m3 dedup threshold was calibrated (17.0 L2) against
  unnormalized vectors, but Ollama's `/api/embed` returns unit-normalized
  vectors for bge-m3 (max possible L2 is √2 ≈ 1.414). Every `<17.0`
  dedup check therefore passed, causing every new memory to be redirected
  to whichever md file already existed in that scope — effectively
  overwriting the first memory ever written in each scope with every
  subsequent write's content. Fresh calibration against real duplicate /
  paraphrase / unrelated pairs lands on 0.5 as the new threshold:
  exact dup (L2=0.00) and paraphrase (L2~0.67) pass; same-topic (L2~1.03)
  and unrelated (L2~1.07) do not.
- Ollama embedder docstring said "unnormalized vectors"; updated to
  reflect Ollama's current behaviour. The L2 distance metric stored in
  each archive's `meta` table is still valid (L2 on unit vectors is a
  monotonic function of cosine distance), so no DB migration is required
  — only the threshold comparison changes.

## [0.2.4] — 2026-04-20

### Fixed

- **Critical:** the curator had been silently dropping every memory decision since v0.1 because the prompt asks Haiku for `{action, name, content, type}` but `_apply_decisions` read `{action, slug, text, kind}`. The 0.2.2 bare-list parser fix + 0.2.3 KeyError guard surfaced this shape mismatch by logging "dropping write_md with missing slug/text" on every turn — the write was never happening. Now `_apply_decisions` reads both shapes via `d.get("slug") or d.get("name")` (with `.md` auto-appended to bare names), `d.get("text") or d.get("content")`, `d.get("kind") or d.get("type")`.
- The curator never implemented `update_md` — the prompt documents it as the preferred action for overwriting an existing memory, but the worker only handled `write_md` and `archive_turn`. Added `update_md` as an alias for the write path (slug collision → overwrite in place, which is the same behaviour as `write_md` + dedup-redirect hitting the exact slug) and `insert_archive` as the prompt-documented name for what the code calls `archive_turn`.
- `skip_all` decisions now log a single INFO with the reason instead of falling through to "ignoring decision with action=...". Cosmetic but clearer in `claude-almanac tail`.

### Operational note

Archives written before 0.2.4 are empty. If you were relying on auto-curation, nothing was getting saved. From 0.2.4 on, the next Stop-hook firing will actually write memories. Verify with `claude-almanac status` — the archive counts should start climbing after your next session ends.

## [0.2.3] — 2026-04-20

### Fixed

- Curator crashed with `KeyError: 'slug'` when Haiku emitted a `write_md` decision missing the `slug` or `text` keys. After 0.2.2 accepted bare-list payloads, more malformed-but-structurally-valid decisions reached `_apply_decisions` and surfaced this gap. Missing keys now log a warning and the decision is skipped; unknown actions log and continue.
- `claude-almanac tail` required a `--` separator before `--no-follow` / `--lines` / `--since` / `--source` because the subparser collected everything as positional. Flags are now declared on the subparser and parsed before dispatch, so `claude-almanac tail --no-follow --lines 40` works as expected.
- `.claude-plugin/marketplace.json` was never bumped during release, so it stayed at `0.1.2` while `plugin.json` advanced. Claude Code's Stop hook intermittently errored with "Plugin directory does not exist" when auto-update of the plugin raced against the marketplace-manifest version mismatch. Marketplace JSON now tracks the plugin version.
- Auto-upgrade hook (`SessionStart` drift detection) had two silent-failure modes: it shelled out to `uv tool upgrade claude-almanac` without pinning the index (so users with pinned corporate mirrors would loop-fail in the background), and the `Popen` returned immediately, so failed upgrades never surfaced to the user on subsequent sessions. The hook now spawns `claude_almanac.hooks.upgrade_runner` which runs `uv tool upgrade --default-index https://pypi.org/simple/ claude-almanac` and records `{ts, exit, target}` to `logs/upgrade.status.json`. On the next session, if the last attempt for the current plugin version failed, the hook surfaces the failure with the exit code + manual recovery command instead of silently spawning another doomed subprocess.

## [0.2.2] — 2026-04-20

### Fixed

- Curator silently dropped decisions when Haiku returned a bare JSON array (`[{...}]` instead of `{"decisions": [...]}`) or when it wrapped the payload in a ```json ... ``` markdown fence. Both shapes are now accepted alongside the documented envelope via a new `_parse_decisions` helper that strips fences and tolerates list-or-dict roots. Previously, bare-list responses raised `AttributeError` inside the outer try/except and bare-fenced responses hit `JSONDecodeError`; both dropped the turn's memories even when the LLM had made valid write decisions.

## [0.2.1] — 2026-04-20

### Fixed

- CI + release integration job's container health check used `curl`, which the `ollama/ollama:latest` image does not ship, so the service never reported healthy and the job never ran. Health check removed; the "Pull bge-m3" step's retry loop (from the runner host, which has curl) handles readiness. 0.2.0 was tagged but blocked at the PyPI publish gate by this bug; 0.2.1 carries the same code as 0.2.0 plus the workflow fix.

## [0.2.0] — 2026-04-20

### Added

- `recall pin`, `recall unpin`, `recall forget`, `recall export` land end-to-end (no more v0.1 "deferred" stubs). `forget` moves memories to a `trash/` dir rather than deleting; `export` concatenates scope markdown with `# scope/slug` headers.
- `claude-almanac status` now surfaces archive counts + pinned counts, last digest mtime, scheduler unit state (digest / server / codeindex-refresh), Ollama reachability, and `EmbedderMismatch` warnings across both scope DBs.
- `claude-almanac calibrate <provider> <model> <fixture.jsonl>` — first-class wrapper around the embedder calibration harness with ASCII histogram + `max × 1.2` threshold suggestion.
- `claude-almanac tail` interleaves `curator.log`, `code-index.log`, `com.claude-almanac.digest.log`, and `com.claude-almanac.server.log` with `[source ts]` prefixes; supports `--follow/--no-follow`, `--lines`, `--since`, `--source`.
- Integration smoke suite: retrieve→curate→recall round trip, codeindex init→search, digest generate→serve round trip. Runs on PRs targeting `release/*` branches; PyPI publish now `needs: [build, integration]`.

### Changed

- Curator transcript parser surfaces `{"type": "summary"}` (compaction) and `{"type": "subagent_stop"}` events as their own pseudo-turns instead of silently dropping them.
- Digest reads commits from the repo's primary branch (`origin/HEAD` → `main` → `master` → HEAD fallback) and fetches `origin/*` before scanning, so feature-branch checkouts no longer cause the digest to miss mainline work.
- Ollama embedder uses split timeouts (`connect=5s`, `read=120s`, `write=30s`, `pool=30s`) so unreachable hosts fail fast while cold-loads of `bge-m3` don't time out.

### Fixed

- launchd always-on units ship with `ThrottleInterval=30` to cap runaway respawn loops.

## [0.1.2] — 2026-04-20

### Added

- Daily code-index refresh job. Set `code_index.daily_refresh: true` in `config.yaml` and run `claude-almanac setup` to register `com.claude-almanac.codeindex-refresh`, a launchd/systemd unit that runs `claude-almanac codeindex refresh --all` at `code_index.refresh_hour` (default 04:00). Walks every repo in `digest.repos`, auto-running `init` on DBs that don't exist yet.
- `claude-almanac codeindex refresh --all` iterates all configured repos in one shot, skip-continue on per-repo failure (matches digest generator semantics). Replaces the manual "cd each repo, rerun" loop.
- `SessionStart` hook (`claude-almanac-upgrade-hook`) detects drift between the plugin version and the installed CLI version. By default, prints a one-line notice telling the user how to upgrade. With `auto_upgrade: true` in `config.yaml` (opt-in), background-launches `uv tool upgrade claude-almanac` on drift so `/plugin update claude-almanac` alone keeps both halves in sync. Non-uv installers get the notice path only.

### Changed

- `claude-almanac setup` now materializes any missing config keys with defaults and rewrites `config.yaml` in canonical order, so additive schema changes (like this release's `daily_refresh`, `refresh_hour`, `auto_upgrade`) don't require hand-editing yaml.
- Setup stamps the installed CLI version at `<data_dir>/.installed_version` so future tooling can detect out-of-band upgrades.

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
