# Changelog

All notable changes to claude-almanac will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## 0.4.3 — 2026-04-21 — Hotfix: docs/** glob on Python &lt;3.13

### Fixed

- `documents/ingest._discover` now normalizes bare `**` patterns (e.g.
  `docs/**`) to explicit `docs/**/*.md` + `docs/**/*.mdx` globs before
  calling `Path.glob`. Python 3.12's `Path.glob("docs/**")` matches only
  directories (3.13+ matches files too), which caused the
  `test_doc_retrieval_smoke` integration gate to fail on the release
  CI runner and blocked PyPI publish for v0.4.0, v0.4.1, and v0.4.2.
  User-facing `patterns:` configs using `docs/**` shorthand now work
  identically across Python 3.11–3.14.

## 0.4.2 — 2026-04-21 — Claude Agent SDK curator provider

### Added

- **`claude_agent_sdk` curator provider** — new curator backend that runs
  against Claude (e.g. Haiku 4.5) via the `claude-agent-sdk` package,
  authenticating with `CLAUDE_CODE_OAUTH_TOKEN` (no Anthropic API key
  required). Suitable for users with a Claude subscription who want
  higher-quality structured-JSON curation than local Ollama models
  provide. Stop-hook curation runs in a background fork, so the
  ~8–10s per-call subprocess warm-start is acceptable.

  Enable via `~/.config/claude-almanac/config.yaml`:

  ```yaml
  curator:
    provider: claude_agent_sdk
    model: claude-haiku-4-5-20251001
    timeout_s: 120
  ```

  The factory recognizes the new provider alongside `ollama`,
  `anthropic_sdk`, `claude_cli`, and `codex`.

## 0.4.1 — 2026-04-21 — Hotfix: wire doc ingest into content init/refresh

### Fixed

- `claude-almanac content init` and `content refresh` now actually run
  the documents-subsystem ingest. v0.4.0 shipped with the CLI
  commands calling only the sym pass; `recall docs` returned
  `(no matches)` for anyone using the stock CLI flow because the
  `content-index.db` never accumulated doc rows. The integration smoke
  test (which calls `documents.ingest.index_repo` directly) did not
  catch the gap. Adding test coverage for the CLI dispatch path.

## 0.4.0 — 2026-04-21 — Documents subsystem + content-index engine refactor

### Added

- **Documents subsystem** — per-repo markdown indexing (`*.md`, `*.mdx`) with
  ATX heading-primary chunking (via `markdown-it-py`) and sliding-window
  fallback for oversized sections. Unified three-section retrieval:
  memories + code + docs share the same autoinject gate as code. New CLI:
  `claude-almanac recall docs <query>`; `recall search` now includes a
  Docs section.

### Changed

- **Content-index engine refactor** — retrieval plumbing (sqlite-vec ops,
  RRF fusion, hybrid channel, low-confidence filter, vector demotion)
  extracted from `codeindex/` into a new shared `contentindex/` package.
  Code and documents are now peer subsystems on the same engine. Per-kind
  `ScoringProfile` dataclass pulls code-specific rules (structural-symbol
  penalty, single-line-var penalty, vector demotion) out of the shared
  engine; `CODE_PROFILE` preserves v0.3.14 behavior, `DOC_PROFILE` starts
  as a no-op.

- **DB rename** — `code-index.db` → `content-index.db` per repo; new
  `idx_entries_doc_key` unique index on `(file_path, line_start)` for
  `kind='doc'` (partial index also guards against NULL `file_path` /
  `line_start` at the schema level as defense-in-depth).

- **Config rename** — global `code_index:` → `content_index:`; adds
  `docs_autoinject: true` flag. Repo-local config filename is unchanged
  (still `.claude/code-index.yaml`); that file gains an optional `docs:`
  section with defaults (patterns: `docs/**`, `README.md`, `CHANGELOG.md`,
  `*.md`). `DocsCfg` dataclass loads the section.

- **CLI rename** — `claude-almanac codeindex ...` → `claude-almanac
  content ...`. No alias; author renames. The launchd/systemd daemon unit
  also rebrands from `com.claude-almanac.codeindex-refresh` to
  `com.claude-almanac.contentindex-refresh`; `claude-almanac setup` detects
  and removes the legacy unit on re-install.

### Fixed

- Markdown extractor's early regex-based heading parser mis-split on `#`
  comments inside fenced code blocks. Swapped to `markdown-it-py`; ATX-only
  (setext headings explicitly ignored so YAML frontmatter closing `---`
  doesn't false-split).

- `contentindex.db.upsert` now guards each `kind`'s key fields against
  NULL: `kind='sym'` requires `symbol_name + file_path`, `kind='doc'`
  requires `file_path + line_start`, `kind='arch'` requires `module`.
  Prevents silent duplicate accumulation under the partial unique
  indexes.

- Sliding-window doc chunks now use a `seen` set to force distinct
  `line_start` per part, closing a case where short-line-range sections
  with long character bodies produced colliding keys.

- `documents/ingest.py` logs structured `doc.embed_fail` events instead
  of silently swallowing embedder exceptions (parity with
  `codeindex/sym.py`).

### New dependency

- `markdown-it-py>=3.0` (CommonMark parser used by the documents subsystem).

### Breaking (manual migration — single-user project)

1. Rename per-repo DB: `mv <project-dir>/code-index.db
   <project-dir>/content-index.db` — or just re-run
   `claude-almanac content init` after upgrading.
2. In `~/.config/claude-almanac/config.yaml`, rename the `code_index:`
   key to `content_index:`. Add `docs_autoinject: true` if you want doc
   hits auto-injected (default is True when the section exists).
3. Re-run `claude-almanac setup` to reinstall the daemon unit under the
   new name. The installer detects and removes the legacy
   `com.claude-almanac.codeindex-refresh` unit automatically.

### Polish (bundled pre-release)

- `recall docs` now uses a `## Relevant docs` top-level header in
  doc-only output (instead of `## Relevant code > ### Docs`);
  `format_doc_hit` drops trailing sentinels when crumb/body are empty.
- Empty `patterns:` list in `.claude/code-index.yaml`'s `docs:` section
  now raises a clear error instead of silently disabling ingest.
- `documents/refresh.py` replaced per-file `ORDER BY created_at` lookups
  with a single `GROUP BY MAX` query.
- Log file `code-index.log` renamed to `content-index.log`;
  `claude-almanac tail code-index` still works and falls back to the
  legacy path if no new-path entries exist yet.
- `cli/setup.py` narrows the legacy-unit uninstall `contextlib.suppress`
  from `Exception` to `(FileNotFoundError, OSError, SubprocessError)`
  so real failures surface.

### Out of scope (v0.4.1)

Plugin API surface, `document-drift` analyzer, doc-specific autoinject
signal detection, YAML frontmatter extraction, setext-heading support.
All deferred pending two-subsystem dogfood.

## 0.3.14 — 2026-04-21 — Retrieval quality fixes from the 13-query dogfood probe

### Fixed

- **Pattern A — module-symbol hijack.** Code-index keyword search now
  penalizes rows whose `symbol_name` didn't match any query token.
  Structural names (`LOGGER`, `__init__`, `__all__`, `__main__`,
  `dispatch`, `main`) get a 0.4× multiplier and single-line module-
  level variables get 0.6×, so `LOGGER` / `MAX_TRANSCRIPT_CHARS` /
  `__init__` no longer hijack top-3 slots when the query only matches
  a file path. Dogfood Q1 ("hook entrypoint user prompt submit") flips
  from `curate.main, retrieve.run, rollup.main` to
  `retrieve.run, autoinject.should_query, rollup.run_hook`. The rule
  is name-only (not body-level) because the extractor occasionally
  bleeds adjacent symbol signatures into the `text` field.
- **Pattern A (vector-channel companion).** The keyword penalty alone
  didn't stop `LOGGER` surfacing at rank 2-3 when the vector embedding
  ranked it high on its own (observed on expanded dogfood: `LOGGER`
  at d=0.746 for "session rollup idle timeout trigger"). The vector
  channel now demotes structural-named hits with no query-name match
  to the end of the pre-fusion list, dropping their RRF contribution
  without removing them entirely. Counter-queries that name LOGGER
  explicitly still return it at rank 1.
- **Pattern D — TypeScript build-output duplication.** Added
  `**/.output/**` and `**/*.d.ts` to the code-index default excludes so
  generated declaration files don't double every symbol hit. Nuxt/Nitro
  `.output/` joins `dist/` and `build/` already in the list.
- **Pattern E — no-confidence false positives.** Vector-only sym hits
  whose distance exceeds an embedder-specific confidence floor are
  dropped before RRF fusion so no-match queries ("blockchain wallet",
  "auth") return the existing `(no matches)` sentinel instead of the
  3 nearest unrelated symbols. Calibrated thresholds: qwen3-embedding
  (any size) / bge-m3 → 0.95 L2; openai / voyage → 0.5 cosine. Hits
  confirmed by the keyword channel bypass the filter.

### Config additions

- `retrieval.code.min_confidence_distance` — per-call override of the
  Pattern E floor. Defaults to `None` (use the embedder profile);
  ≤ 0 disables the filter entirely.
- `EmbedderProfile.min_confidence_distance` — profile-level default
  used when the config override is unset.

### Note

All three fixes are keyword/scoring/index-enumeration changes;
`retrieval.code.hybrid_enabled: false` restores pre-v0.3.11 behavior
if any regression surfaces. The 13-query probe is locked as
regression tests in `tests/unit/codeindex/test_retrieval_quality_probe.py`.

## 0.3.13 — 2026-04-21 — Fix stale integration-test assertion (unblocks 0.3.12 publish)

### Fixed

- **`test_smoke_memory_roundtrip` expected empty stdout** when the curator
  declined to save, but v0.3.6's unified `recall search` now prints a
  `(no matches)` sentinel in that case. The assertion
  `stdout.strip() == ""` was no longer satisfiable. Widened to accept
  either `"teal"` in the hit text or `(no matches)` as the no-hit
  sentinel. Product behavior unchanged.

### Note

This was a stale test assertion masked by the 0.3.6–0.3.11 integration
gate outages. v0.3.12's CI run was the first successful model-pull + test
run since v0.3.5 and surfaced it. Re-ships 0.3.12's features (hybrid
retrieval + release pipeline fix) via the first CI run that can actually
reach `publish`.

## 0.3.12 — 2026-04-21 — Release pipeline fix (pull qwen3-embedding in CI)

### Fixed

- **Release workflow integration gate.** `release.yml` (and `ci.yml`'s
  integration job) only pulled `bge-m3` + `gemma3:4b`. Since v0.3.9
  flipped the default embedder to `qwen3-embedding:0.6b`, integration
  tests that instantiate an embedder from `cfg.embedder.model` asked
  Ollama for a model that wasn't loaded and got `404 Not Found` for
  `/api/embed`. This blocked the publish gate on every release from
  0.3.6 through 0.3.11 — PyPI has been stuck at 0.3.5. Added an explicit
  `qwen3-embedding:0.6b` pull step ahead of the existing bge-m3 +
  gemma3:4b pulls and bumped the Ollama model-cache key from
  `v1-bge-m3-gemma3-4b` to `v2-qwen3-embedding-bge-m3-gemma3-4b` so the
  stale cache invalidates on next run.

### Note

v0.3.12 contains no product code changes beyond 0.3.11 — it re-ships
0.3.11's hybrid code-index retrieval via a CI pipeline that can actually
reach PyPI. See the 0.3.11 entry for feature details.

## 0.3.11 — 2026-04-21 — Hybrid code-index retrieval (vector + keyword RRF)

### Added

- **Keyword retrieval channel.** `claude_almanac.codeindex.keyword.search`
  matches query tokens against `entries.symbol_name`, `entries.file_path`,
  and the first 200 chars of sym-text via SQLite `LIKE`. Case-insensitive,
  3-char token floor, `%`/`_` wildcards escaped. Scored by count of tokens
  matched across the three columns, tie-broken by shorter `file_path`.
- **Reciprocal rank fusion.** `claude_almanac.codeindex.fuse.rrf` merges
  ranked channels via `Σ 1/(k + rank)` (Cormack et al., SIGIR '09, k=60
  default). No per-channel score normalisation needed — crucial since
  vector distance (qwen3 L2 ~14-29) and keyword match count (integer 1-3)
  are on wildly different scales.
- **Hybrid `search_and_format`.** When `hybrid=True` and a query string is
  provided, the sym channel is served by RRF fusion over vector + keyword
  hits (fetch 2×k per channel for reorder headroom). Arch stays
  vector-only — arch rows have no `symbol_name` and multi-line text makes
  keyword-on-first-line unhelpful.
- **CLI `recall code --no-hybrid`** escape hatch for per-invocation debug
  without touching config.
- **`retrieval.code.hybrid_enabled` config flag** (default `true`).
  `keyword_k` (10) and `rrf_k` (60) also tunable. Pre-0.3.11 configs
  missing the `retrieval.code` block still load with defaults.
- **`scripts/check_changelog.py`** CI invariant: asserts the bumped version
  in `pyproject.toml` has a matching `## <version>` header on top of
  CHANGELOG.md AND the predecessor version's header is still present
  (catches the header-overwrite class of bug that hit v0.3.2 → 0.3.3).

### Fixed

- **`recall` subcommand flag passthrough.** `cli/main.py` now uses
  `argparse.REMAINDER` for recall args so flags like `--no-hybrid` reach
  the subcommand dispatcher instead of being rejected by argparse at the
  top level.

### Dogfood verification

Against 2026-04-21 dogfood corpus (fender / gaffer / k-repo):

| Query | v0.3.10 top-3 | v0.3.11 top-3 |
|---|---|---|
| gaffer `tui` | TestRubrics, Baseline, Regression (0/3 TUI) | TestRubrics, **Model (tuireport)**, Regression |
| k-repo `segmentation` | chat/intent_router noise (0/3 in domain) | 3/3 inside `segmentation/segments_analyst/` |
| fender `React component` | 3/3 test utilities | 2 test utilities + 1 toast type (mild churn, acceptable) |
| gaffer `--no-hybrid tui` | N/A | matches v0.3.10 (escape hatch works) |

Floor-raising change on degenerate terse queries; mild ranking churn on
already-good queries — expected RRF tradeoff. Rollback via
`retrieval.code.hybrid_enabled: false` in config or `--no-hybrid` flag.

## 0.3.10 — 2026-04-21 — Curator JSON robustness (schema-constrained + tolerant fallback)

### Fixed

- **Ollama curator now uses JSON-schema-constrained decoding** (`format:
  <schema>` instead of the older `format: "json"`). The shape is a
  permissive `{"decisions": [{...}]}` contract. Grammar enforcement at
  token-gen prevents malformed JSON — notably the unescaped-inner-quote
  bug where gemma4:e4b emitted `"Engineer's Ops Console"` without
  escaping the inner `"`, breaking JSON parse at char ~1099. That
  specific class of curator failure is now impossible: the model
  literally can't emit an unescaped `"` inside a string value.
- **Tolerant parser fallback in `_parse_decisions`.** For providers that
  don't support grammar-constrained decoding (Anthropic SDK, claude_cli,
  codex) or older Ollama versions, `_recover_unescaped_quotes` walks
  the failed JSON, distinguishes structural `"` (followed by `,`, `}`,
  `]`, `:`, or EOF) from genuine-inner-content `"`, and auto-escapes the
  latter before a retry. Conservative by design — an unbalanced string
  or ambiguous shape returns None and the original warning fires.

### Dogfood verification

Live-invoked the curator on a quote-heavy synthetic transcript
mentioning `"Engineer's Ops Console"` — exactly the failure mode from
the 2026-04-21 13:14:28 log entry. gemma4:e4b now emits `\"Engineer's
Ops Console\"` (inner quotes escaped); the output parses cleanly on
first try; no recovery needed.

## 0.3.9 — 2026-04-21 — Qwen3-Embedding profile (free + multi-purpose + code-aware)

### Added

- **Profile entries for `qwen3-embedding:{0.6b,4b,8b}`**. Alibaba's
  Qwen3-Embedding family is officially on the Ollama library, free,
  trained for text + code + cross-lingual retrieval in one model,
  and scores ~70.58 MTEB at the 8B size (beating bge-m3 ~68.5).
- **Live-verified on this repo:** `qwen3-embedding:0.6b` hits 5/5
  dogfood queries (vs bge-m3's 4/5 even after the v0.3.8 sym-text
  enrichment). The one bge-m3 missed — `"archive migration schema"` —
  returns `ensure_schema` at rank #1 with qwen3. Same 1024 dim as
  bge-m3, so archive/code-index vec tables are wire-compatible.

### Upgrade path

Qwen3 is a swap-in replacement for bge-m3 on the archive schema side
(same dim) but `archive.assert_compatible` fails-loud on model mismatch
— by design, since the vector space is different and cross-embedder
search returns garbage. Users who want to upgrade:

1. `ollama pull qwen3-embedding:0.6b` (or `4b` / `8b` — see sizes below)
2. Edit `~/.config/claude-almanac/config.yaml`:
   ```yaml
   embedder:
     provider: ollama
     model: qwen3-embedding:0.6b
   ```
3. Rebuild existing indexes:
   - Archives: delete `archive.db` files under
     `<data_dir>/{global,projects/*}/`, then `claude-almanac setup`
     (re-ingests memories from the `.md` files alongside).
   - Code indexes: delete `code-index.db` files, then
     `claude-almanac codeindex init` per-repo.

Size tradeoffs:

| Variant | Params | Dim | Use case |
|---|---|---|---|
| `qwen3-embedding:0.6b` | 600 M | 1024 | Drop-in for bge-m3 users |
| `qwen3-embedding:4b`   | 4 B   | 2560 | Higher retrieval quality; vec rebuild required |
| `qwen3-embedding:8b`   | 8 B   | 4096 | MTEB-leading quality; full rebuild |

bge-m3 remains the shipped default — changing it would force every
user to rebuild every archive + code-index without warning. This
release only adds the profile so users who opt in don't have to
hand-configure `dedup_distance` / `rank_band`. A follow-up release
may ship an automated `claude-almanac migrate-embedder` command to
rebuild in-place.

## 0.3.8 — 2026-04-21 — Code-index retrieval quality (enriched sym text)

### Changed

- **`codeindex/sym.py::compose_text` now embeds a header line** with
  `file_rel`, `kind`, and `name` in front of the bare signature. Before:
  the sym extractor embedded just `def foo(...)` — a bge-m3 embedding of
  20–80 chars without any path or module context. After: each symbol's
  embedded text starts with e.g.
  `// src/claude_almanac/core/archive.py  [function]  ensure_schema`
  before the signature. General-text embedders (bge-m3, and community
  free alternatives like `nomic-embed-text` / `mxbai-embed-large`) ride
  heavily on natural-language token overlap — path components are the
  strongest semantic anchor available without a code-specialized model.

### Dogfood verification

Re-running the 5 code-retrieval queries against this repo:

- `archive migration schema` previously returned
  `projects_memory_dir / MAX_TRANSCRIPT_CHARS / project_memory_dir` (all
  off-topic). After enrichment: top-3 are all in `core/archive.py`
  (`nearest / prune / init`). Four other queries that already hit
  correctly (curator / rollup / decay / edges) continued to hit.
- Rebuild cost: trivial. 229 symbols re-extracted + re-embedded in
  ~11 s on this repo.

### Migration note

The existing `code-index.db` on disk still holds pre-enrichment embeddings.
Users need a one-time rebuild to benefit:

    claude-almanac codeindex init    # overwrites the stale rows

(No auto-migrate because the schema didn't change, only the embedded
text content did; deciding when to pay for the rebuild is the user's
call. v0.3.7's dim-mismatch migration only fires when the vec
dimension changes.)

## 0.3.7 — 2026-04-21 — Code-index robustness (stale-sha + dim-mismatch)

### Fixed

- **`codeindex refresh` no longer crashes when `last_sha` is gone from the
  repo's git history.** `git diff <last>..<target>` raised
  `CalledProcessError` for force-pushed branches, rewritten history, or
  stale placeholder SHAs from old buggy inits. Refresh now catches that
  and falls back to `changed = []` (equivalent to a fresh index from
  `target`), logs `refresh.stale_last_sha`, and continues.
- **Stale `code-index.db` dim-mismatch auto-renamed on setup.**
  `entries_vec` pins the embedding dimension at creation; older installs
  had a bug that wrote `FLOAT[2]` instead of the embedder's real dim, and
  legitimate embedder swaps produce the same shape of incompatibility.
  `claude-almanac setup` (fired on every `uv tool upgrade`) now scans
  every project's `code-index.db`, and when one's `entries_vec` dim
  doesn't match the configured embedder profile, renames it aside to
  `code-index.db.stale-<detected-dim>` and prints a note pointing the
  user at `claude-almanac codeindex init` to rebuild. Vectors can't be
  migrated across dims; re-embedding is the only answer.

## 0.3.6 — 2026-04-21 — Unified `recall search` (memories + code-index)

### Added

- **`recall search` now blends archive memories with the current repo's
  code-index.** Both sections render in a single output (memories first,
  then a `## Relevant code` block with symbol hits). Gracefully omits the
  code section when `code-index.db` is missing or empty — never fails
  recall just because the code-index is absent / stale.
- **`recall memories <query>`** + **`recall memories-all <query>`** —
  memory-only variants for users who explicitly want to exclude code
  symbols. `recall code <query>` (code-only) is unchanged.

### Changed

- **Default `code_index.enabled: true` in shipped config** (was `false`).
  Users still need to run `claude-almanac codeindex init` per-repo with a
  `.claude/code-index.yaml` to actually populate an index; the flag only
  governs auto-inject + whether recall-search queries the index.

### Known follow-ups

- **Code-index dim mismatch is not yet auto-healed on upgrade.** Stale
  `code-index.db` files created by very old installs can hold a wrong-dim
  vec table (`FLOAT[2]` instead of the embedder's real dim). Symptom:
  `sqlite3.OperationalError: Dimension mismatch for query vector`.
  Workaround: delete the file and re-run `claude-almanac codeindex init`.
  A follow-up release will extend `setup`'s auto-migration to cover
  code-index dims the same way archive DBs are now handled.

## 0.3.5 — 2026-04-21 — Auto-migrate stale archive DBs on setup

### Fixed

- **`recall search-all` no longer crashes on worktrees / orphaned project
  dirs that hold pre-v0.3.1 archive DBs.** Old DBs without the
  `last_used_at` column or `edges` table made `archive.search` raise
  `sqlite3.OperationalError: no such column: e.last_used_at` as soon as
  the query loop reached one of them. `claude-almanac setup` (fired on
  every `uv tool` upgrade via the upgrade hook) now walks every
  `projects/<key>/archive.db` + `global/archive.db`, runs `ensure_schema`
  on each, and reports how many were migrated. Self-heals without user
  action after upgrade.

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

## 0.3.2 — 2026-04-21 — Session rollups + KG edges (v0.3 §3.1 + §3.3)

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
