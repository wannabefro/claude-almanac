# Changelog

All notable changes to claude-almanac will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## 0.3.4 — 2026-04-21 — Polish (cwd robustness + setup hints + .gitignore)

### Fixed

- **Curator survives a deleted working directory.** Background curator /
  rollup processes inherit cwd from their parent. If that directory was
  removed between fork and run (e.g. a short-lived worktree), `Path.cwd()`
  raised `FileNotFoundError` and took down the whole curator pass. `paths.
  project_key()` now routes through a `_safe_cwd()` helper that returns a
  `cwd-unknown` sentinel key instead of crashing; the curator writes to
  `<projects>/cwd-unknown/archive.db` in that case.
- **Stale `uv.lock` accidentally committed in v0.3.3.** Added to `.gitignore`
  and removed from tracking. The repo no longer pins resolved versions in
  VCS.
- **Digest web-UI mode selector** now reads `fast (configured provider)`
  and `deep (tools — requires \`claude\` CLI)`. Makes the deep-mode
  Claude-binary dependency discoverable without reading docs.

### Added

- **`setup` prints available curator providers** when `claude` / `codex` /
  `ANTHROPIC_API_KEY` are present on the machine. Info-only — does not
  change config. Surfaces the rollout options (`rollup.provider`,
  `digest.narrative_provider`, `digest.qa_provider`) so users don't need
  to discover them from docs.

## 0.3.3 — 2026-04-21 — Digest polish (kind resolution + Q&A provider unification)

### Fixed

- **Daily digest no longer shows every new memory as `[unknown]`.** Curator
  has been writing bare markdown bodies (no YAML frontmatter) since v0.2.x,
  so the digest collector's `fm.get("type", "unknown")` always fell through.
  The collector now resolves kind via a chain: frontmatter → archive DB
  lookup (`SELECT kind FROM entries WHERE source = 'md:<filename>'`) → slug
  prefix heuristic (`feedback_`, `project_`, `reference_`, `user_`) →
  `unknown` only as a last resort.
- **Fast-mode digest Q&A works without the `claude` binary on PATH.**
  Previously `claude-almanac digest ask` on the web UI subprocessed
  `claude -p --model <m>` directly and crashed with "claude binary not
  found" on machines that had the older provider layout. The Q&A path now
  routes through `curators.factory.make_curator`, so any configured
  provider (ollama, anthropic_sdk, claude_cli, codex) can answer questions.

### Added

- **`digest.qa_provider` / `digest.qa_model` config overrides.** Dedicated
  Q&A tuning knobs with the fall-through chain `qa_*` → `narrative_*` →
  `cfg.curator`. Useful when users want a low-latency interactive provider
  (e.g. `ollama`) for Q&A while keeping a slower, higher-quality provider
  (e.g. `codex`) for once-per-day narratives.

### Notes

- Deep-mode Q&A (`mode=deep`) still requires the `claude` binary because
  it's built on `claude-agent-sdk`, which drives Claude Code's OAuth
  session. No change there.

### Added

- **Session rollups (§3.1).** First-class narrative artifact per work session,
  with `narrative` (2–4 paragraphs), `decisions` (non-obvious choices with
  rationale), and `artifacts` (files/commits/memories touched). Produced by
  a new `RollupGenerator` that reuses the curator provider factory but has
  its own prompt. Stored in a new `rollups` table + `rollups_vec` vector
  table.
- **Rollup triggers.** `SessionEnd` and `PreCompact` Claude Code hooks fire
  the rollup runner; `UserPromptSubmit` checks for an idle prior session
  (default 45 min threshold) and retroactively rolls it up; explicit
  `claude-almanac recall rollup-now` for manual invocation.
- **Rollup retrieval (gated).** `retrieval.rollups.autoinject: false` by
  default. `claude-almanac recall rollups <query>` for on-demand recall.
  Digest web UI gains a `/rollups` tab with per-rollup detail views.
- **Knowledge-graph edges (§3.3).** New `edges` table with four types:
  `related`, `supersedes`, `applies_to`, `produced_by`. Fully-qualified
  scope strings (`entry@project`, `entry@global`, `rollup@project`) travel
  with every edge.
- **Edge creation paths.** Curator emits `related` via an extended JSON
  contract (`"edges": [{"type": "related", "to": "<slug>"}]`); dedup emits
  `supersedes` when an `update_md` changes the live body; rollup generator
  emits `produced_by` for each memory written during the session window;
  user emits all four via CLI.
- **Edge retrieval (gated).** `retrieval.edges.skip_superseded: true`
  (default ON) hides explicitly-replaced entries. `retrieval.edges.expand:
  false` adds 1-hop graph-walk expansion with bonus re-scoring.
- **CLI.** `recall link`, `recall supersede`, `recall unlink`, `recall
  links`, `recall rollups`, `recall rollup-now`.
- **Status.** `/almanac status` shows rollup count-by-trigger + edge
  count-by-type with a cross-scope edge counter.
- **`claude_cli` curator provider.** Invokes `claude -p --model <model>`
  as a subprocess using the user's Claude Code OAuth session — no
  `ANTHROPIC_API_KEY` required. CLI boot makes it unsuitable for the
  per-turn curator hot path, but it shines as a rollup/digest provider.
- **`codex` curator provider.** Invokes `codex exec` non-interactively
  using the user's Codex login (no API key required). Same CLI-boot
  tradeoffs as `claude_cli`. Routes through
  `--skip-git-repo-check --ephemeral -s read-only` for safety.
- **`rollup.model` config override.** Lets users pick a different model
  for rollups than the per-turn curator without touching `curator.model`
  (e.g. `curator=gemma4:e4b` but `rollup=qwen2.5:7b` or
  `rollup.provider=codex`).
- **`digest.narrative_provider` / `digest.narrative_model` config
  overrides.** Daily-digest commit narratives now route through the
  same `curators.factory.make_curator()` as the per-turn curator and
  rollup generator, so all three LLM-text surfaces share one provider
  abstraction and can be independently configured per feature.

### Fixed

- **Curator non-JSON log.** Widened from `%.200s` to full-payload logging
  so truncation can be diagnosed in future; previously hid whether failures
  were truncation or shape drift.
- **Ollama `num_predict: 8192`.** Lifted from the default (~2k) to
  accommodate the curator's longest observed payloads. Rollup generator
  reuses the same bumped setting.
- **`rollup.provider` auto-default.** When `ANTHROPIC_API_KEY` is set,
  rollups prefer `anthropic_sdk` over Ollama for higher JSON reliability on
  longer narrative outputs. Explicit `rollup.provider:` in config overrides.
- **`archive.prune()` edge cascade.** Pruned entries now also remove their
  attached edges (prevents orphans). `prune()` gains a `scope` parameter
  to correctly cascade against `entry@project` or `entry@global` archives.
- **`archive.init()` v0.3.2 tables.** Fresh-DB init now creates `edges` +
  `rollups` + `rollups_vec` (previously only the migration path did).
- **`_migrate_schema` fail-loud.** Raises `ValueError` when the `meta`
  table has no `dim` key instead of silently defaulting to 1024.
- **cwd-path encoding for transcript discovery.** Claude Code replaces
  both `/` and `.` in the cwd when deriving the project-transcript
  directory name; `rollup-now` and the idle-fallback previously only
  replaced `/`, missing transcripts for any cwd containing a dot.
- **Digest narrator unification.** `digest/render.py::haiku_narrate`
  no longer shells out directly to `claude -p` via a private helper.
  It now takes a `Curator` instance from the factory, so digest
  narratives honor `cfg.curator` (or the new `digest.narrative_*`
  overrides). Falls back to bare `sha subject` bullets when the
  curator returns empty.

### Schema (idempotent, auto-migrated)

- New `rollups` table (`session_id, repo_key, branch, started_at,
  ended_at, turn_count, trigger, narrative, decisions, artifacts,
  created_at`) with `UNIQUE(session_id, trigger)`.
- New `rollups_vec` virtual table (vec0, dim from embedder profile).
- New `edges` table (`src_id, src_scope, dst_id, dst_scope, type,
  created_at, created_by`) with `UNIQUE(src_id, src_scope, dst_id,
  dst_scope, type)`, indexed on both directions.

## 0.3.1 — 2026-04-20

### Added
- **Temporal decay ranking** (`retrieval.decay.enabled`, default on). Reorders
  tied-distance hits by usage recency using Ebbinghaus-style
  `(use_count + 1)^β · exp(-λ · Δt)`. Gated; flip `enabled: false` to restore
  v0.3.0 pure-distance sort.
- **Reinforcement on auto-inject**: `use_count` increments and `last_used_at`
  updates for every memory actually surfaced by the UserPromptSubmit hook.
- **Memory versioning**: dedup redirect and `update_md` decisions now snapshot
  the prior body to a new `entries_history` table. One live `entries` row per
  slug. Append-only; no destructive overwrites.
- **`claude-almanac recall history <slug>`** — print the version chain.
- **`claude-almanac recall correct <slug> [--body TEXT]`** — explicitly supersede
  a memory. Opens `$EDITOR` when `--body` is not supplied.
- **`/almanac status`** now shows live entry count, historical-version count,
  and current decay parameters.

### Changed
- **`archive.prune()`** now evicts based on decay score below
  `retrieval.decay.prune_threshold` (default 0.05), with a 30-day safety floor
  (`retrieval.decay.prune_min_age_days`). Pinned memories remain immune. Note:
  `archive.prune()` is still a library function with no automatic caller —
  users invoke it manually.

### Schema (idempotent, auto-migrated by `archive.init()`)
- `entries.last_used_at INTEGER` (nullable)
- `entries.use_count INTEGER NOT NULL DEFAULT 0`
- New `entries_history` table (slug, text, kind, version, original_created_at,
  superseded_at, provenance) + index on `(slug, version)`.

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

### Notes

- Default local model is `gemma3:4b` (~3 GB, 4.3 B parameters). `gemma4:e4b` (~8 GB, 8 B) is a viable opt-in via `curator.model: gemma4:e4b` — parity tests pass across all four fixtures, memory bodies are slightly better structured, but per-invocation latency is 3–5× higher and the larger context makes the model more susceptible to bleed from `{{EXISTING_MEMORIES}}` into unrelated decisions. Pick gemma3 for throughput, gemma4 for prose quality.

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
