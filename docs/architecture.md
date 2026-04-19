# Architecture

claude-almanac ships three subsystems that share storage and configuration but run independently:

```
┌──────────────────────── Claude Code ────────────────────────┐
│                                                             │
│  UserPromptSubmit ─────┐             ┌── Stop hook          │
│  hook                  │             │                      │
│                        ▼             ▼                      │
│             claude_almanac.hooks.retrieve   claude_almanac.hooks.curate
│                        │             │                      │
└────────────────────────┼─────────────┼──────────────────────┘
                         │             │
                         ▼             ▼
                    ┌─────────────────────────┐
                    │   claude_almanac.core   │
                    │  (archive + retrieve +  │
                    │   curator + config)     │
                    └──┬───────────┬──────┬───┘
                       │           │      │
               ┌───────▼──┐   ┌────▼─┐   ┌▼───────────┐
               │embedders │   │ code │   │  digest    │
               │ (ollama, │   │index │   │(generator, │
               │  openai, │   │      │   │ server,    │
               │  voyage) │   │      │   │ Q&A)       │
               └──────────┘   └──────┘   └────────────┘
                       │           │           │
                       ▼           ▼           ▼
                  ┌──────────────────────────────────┐
                  │  XDG data dir (SQLite + MD)      │
                  │  global/ projects/<key>/         │
                  │  digests/ activity.db            │
                  │  code-index.db logs/             │
                  └──────────────────────────────────┘
```

## Three subsystems

### 1. Memory (core/)

- **Archive DB** (`core/archive.py`) — SQLite with `sqlite-vec` vectors. One DB per scope: `global/archive.db` + `projects/<git-key>/archive.db`. Stores `embedder_name`, `model`, `dim`, `distance` in a `meta` table; reads enforce match or raise `EmbedderMismatch`.
- **Retrieve** (`core/retrieve.py`) — called by the `UserPromptSubmit` hook on every turn. Embeds the prompt, queries top-k from global + project archives, and (if the auto-inject gate fires) appends a `## Relevant code` block from the code-index DB.
- **Curator** (`core/curator.py`) — invoked via the `Stop` hook (which fork-execs a detached background worker). Parses the JSONL transcript tail, sends it to Haiku via the `claude -p` CLI, and applies the returned decisions (`write_md` for structured memories; `archive_turn` for unstructured archive entries). Dedup uses the per-embedder distance threshold.
- **Paths** (`core/paths.py`) — XDG resolution for `data_dir()`, `config_dir()`, `global_memory_dir()`, `project_memory_dir()`. The per-project key is a sha256 hash of the parent of `git-common-dir` (so worktrees share state).

### 2. Code index (codeindex/)

See [docs/codeindex.md](codeindex.md) for the full writeup. Summary:

- **`sym` pass** — extracts public symbol signatures (AST for Python, tuned regex for TS/Go/Java, Serena fallback for other languages), embeds them, writes to `code-index.db`.
- **`arch` pass** — optional LLM-powered module-level summaries; sends source content to Anthropic via `claude` CLI. Dual trust-boundary gate (repo-local + global config).
- **Auto-inject** — retrieve hook surfaces code-index hits alongside memory hits when prompt signals suggest a code question.
- **CLI** — `claude-almanac codeindex {init,refresh,arch,status}`; also `recall code <query>` for direct search.

### 3. Digest (digest/)

- **Generator** (`digest/generator.py`) — daily job. Collects 24h of activity via `digest/collectors.py` (memory changes, retrieval log, git commits), embeds commits into `activity.db`, renders markdown via Haiku, writes `digests/<repo>/YYYY-MM-DD.md`, notifies.
- **Server** (`digest/server.py`) — FastAPI on `127.0.0.1:8787`. Routes: `/` (home), `/today`, `/digest/{date}`, `/digest/{repo}/{date}`, `/digests`, `/generate`, `/ask` (fast GET), `/ask/stream` (deep SSE), `/health`.
- **Q&A** (`digest/qa/`) — pluggable tool registry. Fast mode = single tool call + answer. Deep mode = multi-hop resolver with diff + cross-artifact tools. Auto-discovers tool modules in `digest.qa.tools` (and, when codeindex is installed, `codeindex.digest_tools`).

## Hooks flow

### UserPromptSubmit (every turn)

```
user types prompt
  ↓
Claude Code fires UserPromptSubmit hook with {prompt, session_id, cwd, ...}
  ↓
python -m claude_almanac.hooks.retrieve reads the JSON from stdin
  ↓
core.retrieve.build_injection(prompt) returns markdown block
  ↓
hook emits the block on stdout — Claude Code appends it to the prompt context
```

Injection is advisory; the LLM is free to ignore it. Budget: ~5 KB, top_k=5 memories by default.

### Stop (end of turn)

```
turn ends
  ↓
Claude Code fires Stop hook with {transcript_path, session_id, cwd}
  ↓
python -m claude_almanac.hooks.curate reads JSON, fork-execs detached worker
  ↓
parent exits ~10ms (Claude Code is never blocked)
  ↓
worker:
  - reads transcript JSONL, concatenates user/assistant turns
  - calls `claude -p --model haiku` with curator-prompt.md
  - parses JSON decisions {write_md, archive_turn}
  - applies: write MD files, dedupe against archive, insert archive rows
```

Fork-exec + detached session means a slow curator never delays the user's next prompt. Lockfile at `logs/curator.lock` prevents rapid-fire pileups.

## Data flow

### Retrieval (every turn)

```
prompt → embedder.embed([prompt]) → sqlite-vec KNN in global + project archive.db
                                  → optional sqlite-vec KNN in code-index.db
                                  → markdown injection block
```

### Curation (end of turn)

```
transcript JSONL → concat user+assistant turns → Haiku → JSON decisions
    ↓
    for each decision:
      embedder.embed([text])
      dedup check against archive.db (distance < threshold → reuse slug)
      write MD file + insert archive row (with vector)
```

### Digest generation (daily)

```
cron-like daily fire (launchd/systemd timer)
  ↓
for each configured repo:
  git log --since=24h → commits
  embedder.embed([commit_message for c in commits]) → activity.db
  collect memory_changes + retrieval_log + commits
  Haiku renders markdown from structured input
  write digests/<repo>/<date>.md
  notify
```

## Where to change X

| I want to… | Look here |
|---|---|
| Add a new embedder | `src/claude_almanac/embedders/<name>.py` + register in `embedders/__init__.py` + profile in `embedders/profiles.py`. See [contributing.md](contributing.md#adding-an-embedder-adapter). |
| Change how memory is dedup'd | `core/dedup.py` (logic) + `embedders/profiles.py` (thresholds) |
| Change what the curator saves | `core/assets/curator-prompt.md` (LLM prompt) + `core/curator.py::_apply_decisions` (decision dispatch) |
| Add a new `/recall` subcommand | `cli/recall.py::run` + `commands/recall.md` (help) |
| Add a new digest Q&A tool | `src/claude_almanac/digest/qa/tools/<name>.py` — decorated with `@tool("name", "desc")`. Auto-discovered. |
| Change the digest UI | `src/claude_almanac/digest/templates/` + `src/claude_almanac/digest/static/` |
| Port to a new OS | `src/claude_almanac/platform/<name>.py` implementing `Scheduler` + `Notifier`. See [contributing.md](contributing.md#adding-a-platform-adapter). |
| Change the auto-inject gate | `src/claude_almanac/codeindex/autoinject.py::signal_count` + `core/retrieve.py::build_injection` |
| Change what data dir is used | Set `CLAUDE_ALMANAC_DATA_DIR` (runtime) or patch `core/paths.py::data_dir` (code) |

## Invariants

1. **Embedder metadata is durable.** Every DB stores `embedder_name/model/dim/distance` in a `meta` table. Mismatches raise `EmbedderMismatch` at read time — no silent corruption.
2. **Trust boundary on arch summaries.** `send_code_to_llm: true` must be set in BOTH the repo-local `.claude/code-index.yaml` AND the global `config.yaml`. Defaults are `false` in both scopes.
3. **Worktree safety.** Per-project state keys off `git-common-dir`'s parent, not `cwd`. Two worktrees of the same repo share memory + code-index DBs.
4. **Hook latency budget.** `UserPromptSubmit` has a ~500ms soft budget; `Stop` has a ~20ms soft budget (the curator runs in a detached fork).
5. **Digest is off by default.** No launchd/systemd units are installed until the user sets `digest.enabled: true` and re-runs `claude-almanac setup`.

## Dependencies

- `sqlite-vec` (vendored via PyPI) — vector search extension for SQLite.
- `httpx` — HTTP client for Ollama/OpenAI/Voyage embedder adapters.
- `jinja2` — renders launchd/systemd unit templates.
- `pyyaml` — config parsing.
- `platformdirs` — XDG path resolution.
- `fastapi` + `uvicorn[standard]` + `sse-starlette` — digest server.
- `markdown` — digest HTML rendering.
- `claude-agent-sdk` — curator + Haiku invocations (primary; `claude -p` CLI is a fallback when SDK is unavailable).

Optional: `openai`, `voyageai`.
