# Config reference

claude-almanac reads `~/.config/claude-almanac/config.yaml` on macOS (respecting `$XDG_CONFIG_HOME`) and `$XDG_CONFIG_HOME/claude-almanac/config.yaml` on Linux (fallback `~/.config/claude-almanac/`). Override the location with `CLAUDE_ALMANAC_CONFIG_DIR`.

The default file is written by `claude-almanac setup` on first run. All fields are optional; unspecified values fall back to the defaults listed below.

## Full schema

```yaml
embedder:
  provider: ollama           # ollama | openai | voyage
  model: bge-m3              # per-provider default: bge-m3 (ollama), text-embedding-3-small (openai), voyage-3 (voyage)
  api_key_env: OPENAI_API_KEY   # cloud providers only; ignored for ollama

digest:
  enabled: false             # true enables the daily digest + server platform units
  hour: 7                    # 0–23, local time; controls when the daily digest runs
  notify: true               # emit a desktop notification when the digest completes
  repos:
    - path: ~/code/myrepo
      alias: myrepo          # shown in the digest UI; defaults to basename of path

code_index:
  enabled: true              # when false, /recall code returns an error and code autoinject is disabled
  send_code_to_llm: false    # TRUST BOUNDARY — opt-in to arch summarization which sends source to Anthropic via claude CLI

retrieval:
  top_k: 5                   # number of memory hits appended to UserPromptSubmit injection
  code_autoinject: true      # append code-index hits to memory hits on code-shaped prompts

thresholds:
  dedup_distance: null       # per-embedder; null = load from profile (recommended); override only if calibrated
```

## Per-field reference

### `embedder.provider` — `string`, default `ollama`

Selects the embedder adapter. Valid values: `ollama`, `openai`, `voyage`. Each adapter must ship a calibration profile (see "Embedder profiles" below). Switching providers requires re-indexing all DBs — `archive.db`, `code-index.db`, `activity.db` — because the stored embedder metadata is checked on read.

Env override: `CLAUDE_ALMANAC_EMBEDDER_PROVIDER`.

### `embedder.model` — `string`, default per-provider

The model name passed to the adapter. For Ollama it's the `ollama pull` name (e.g. `bge-m3`, `nomic-embed-text`). For OpenAI it's the API model name (e.g. `text-embedding-3-small`, `text-embedding-3-large`). For Voyage it's the model ID (e.g. `voyage-3`, `voyage-3-large`).

Env override: `CLAUDE_ALMANAC_EMBEDDER_MODEL`.

### `embedder.api_key_env` — `string`, default `OPENAI_API_KEY` for openai, `VOYAGE_API_KEY` for voyage

Name of the env var holding the API key. Ignored for `ollama`. The adapter reads `os.environ[api_key_env]` at call time, so rotating keys doesn't require a restart.

### `digest.enabled` — `bool`, default `false`

Gates installation of the launchd/systemd units for the daily generator + the always-on FastAPI server. When toggled true-to-false, the next `claude-almanac setup` run uninstalls the units.

Env override: `CLAUDE_ALMANAC_DIGEST_ENABLED`.

### `digest.hour` — `int 0–23`, default `7`

Local-time hour at which the daily generator fires. Captured by the platform unit at install time; changing this requires re-running `claude-almanac setup` to regenerate the unit.

### `digest.notify` — `bool`, default `true`

When true, the generator calls the platform `Notifier` on success (terminal-notifier or osascript on macOS; notify-send on Linux). The notification includes a link to `http://127.0.0.1:8787/today`.

### `digest.repos` — `list`, default `[]`

Each entry is `{path: <absolute-or-tilde-path>, alias: <short-name>}`. The generator processes each repo in order. Missing paths are logged and skipped.

### `code_index.enabled` — `bool`, default `true`

When false, `/recall code` returns an error and the auto-inject gate short-circuits (no code-index query is issued). Useful for repos where the code index is too expensive to maintain.

### `code_index.send_code_to_llm` — `bool`, default `false`

**Trust boundary flag.** When true AND the repo-local `.claude/code-index.yaml` also has `send_code_to_llm: true`, `claude-almanac codeindex arch` will send source file content (up to 20 files × 4 KB per module) to Anthropic via the `claude` CLI. Default false in both scopes; the dual-check prevents a misconfigured repo-local file from leaking source.

The symbol pass (`sym`) never sends source — only embeddings of symbol signatures. See [docs/codeindex.md](codeindex.md#trust-boundary).

### `retrieval.top_k` — `int`, default `5`

Number of memory hits to include in the `## Relevant memories` block appended to each prompt by the `UserPromptSubmit` hook. Hits are ranked across global + current-project archive DBs by distance.

### `retrieval.code_autoinject` — `bool`, default `true`

When true AND the prompt has ≥2 code-signal tokens (backticked identifiers, camelCase, file paths, "how does X work" idioms), the retrieve hook appends a `## Relevant code` block alongside memory hits. See [docs/codeindex.md](codeindex.md#auto-inject-gate) for the full gate logic.

### `thresholds.dedup_distance` — `float | null`, default `null`

The distance below which a curator decision is treated as a duplicate of an existing markdown memory (the curator reuses the existing slug instead of creating a new one). `null` means "load from the embedder's profile" — recommended unless you've run the calibration harness and have a measured override.

For `bge-m3` the profile default is `17.0` (distance space is L2 on unnormalized vectors, ~14–29 range per the calibration work). Do NOT transfer this across embedders; thresholds are embedder-specific.

## Env var overrides

Every top-level scalar supports an env var override of the form `CLAUDE_ALMANAC_<SECTION>_<FIELD>`. For example:

| Field | Env var |
|---|---|
| `embedder.provider` | `CLAUDE_ALMANAC_EMBEDDER_PROVIDER` |
| `embedder.model` | `CLAUDE_ALMANAC_EMBEDDER_MODEL` |
| `digest.enabled` | `CLAUDE_ALMANAC_DIGEST_ENABLED` |
| `digest.hour` | `CLAUDE_ALMANAC_DIGEST_HOUR` |
| `code_index.enabled` | `CLAUDE_ALMANAC_CODE_INDEX_ENABLED` |
| `code_index.send_code_to_llm` | `CLAUDE_ALMANAC_CODE_INDEX_SEND_CODE_TO_LLM` |
| `retrieval.top_k` | `CLAUDE_ALMANAC_RETRIEVAL_TOP_K` |
| `retrieval.code_autoinject` | `CLAUDE_ALMANAC_RETRIEVAL_CODE_AUTOINJECT` |
| `thresholds.dedup_distance` | `CLAUDE_ALMANAC_THRESHOLDS_DEDUP_DISTANCE` |

List/dict fields (`digest.repos`) are YAML-only; no env var form.

Env var parsing: bools accept `1/0`, `true/false`, `yes/no` case-insensitive. Ints and floats parse as Python literals. Unparseable values fall back to the YAML value (or default) and log a warning.

## Embedder profiles

Each embedder ships a calibration profile — a dict of empirical thresholds keyed by `(provider, model)`. Profiles live in `src/claude_almanac/embedders/profiles.py` and are loaded at runtime via `get_profile(provider, model)`.

### Fields per profile

- `name` — `"{provider}:{model}"`, used in logs
- `dim` — vector dimension (must match the embedder's live output or the archive DB rejects inserts)
- `distance` — `"l2"` or `"cosine"` (sqlite-vec metric)
- `dedup_distance` — empirical threshold below which two memories are considered near-duplicates

### Shipped profiles (v0.1)

| Provider | Model | dim | distance | dedup_distance | source |
|---|---|---|---|---|---|
| ollama | bge-m3 | 1024 | l2 | 17.0 | measured over `~/.claude/memory-tools/` fixture corpus (2026-04) |
| openai | text-embedding-3-small | 1536 | cosine | 0.35 | calibrated against same corpus, re-embedded |
| openai | text-embedding-3-large | 3072 | cosine | 0.30 | same |
| voyage | voyage-3 | 1024 | cosine | 0.32 | same |

### Adding a new embedder profile

1. Implement the adapter in `src/claude_almanac/embedders/<provider>.py` (see `docs/contributing.md` for the Embedder protocol).
2. Run the calibration harness against the fixture corpus:

   ```bash
   claude-almanac calibrate --provider <name> --model <model> \
     --corpus tests/fixtures/calibration_corpus.jsonl
   ```

   The harness embeds every pair, emits a distance histogram, and suggests a threshold at the 95th percentile of known-duplicate pairs.
3. Add the profile to `src/claude_almanac/embedders/profiles.py`.
4. Write a unit test covering the new profile lookup (`tests/unit/test_embedders_factory.py` has the pattern).
5. Update this table.

## Re-indexing after config changes

These changes require re-indexing because stored DB metadata no longer matches:

| Change | Affected DBs | Procedure |
|---|---|---|
| `embedder.provider` | archive.db (global + project), code-index.db, activity.db | Delete the files; they're recreated on next write |
| `embedder.model` | same | same |
| `thresholds.dedup_distance` | none (read-time only) | no re-indexing needed |

To re-index safely:

```bash
# Back up first
cp -r "$(claude-almanac path data)" ~/almanac-backup
# Delete DBs (keeps markdown memory files)
find "$(claude-almanac path data)" -name '*.db' -delete
# Re-populate on next Stop hook + next digest run
```
