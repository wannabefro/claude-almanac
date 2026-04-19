# Code index

The code index builds a per-repo vector index of public symbols and optional
module-level architecture summaries. Hits are automatically surfaced alongside
memory hits whenever a user prompt looks like a code question.

## Quickstart

Create `.claude/code-index.yaml` at the root of the repo:

```yaml
default_branch: main
modules:
  patterns:
    - src
    - packages/*
# Optional (default: false). Set true to allow arch summaries, which send
# source content to Anthropic via the `claude` CLI.
send_code_to_llm: false
min_files_for_arch: 3
```

Then run:

```bash
claude-almanac codeindex init
claude-almanac codeindex status
```

Incremental refreshes (suitable for a daily cron/launchd job):

```bash
claude-almanac codeindex refresh
```

Arch summaries (opt-in, LLM-powered):

```bash
# Requires BOTH:
# 1. `send_code_to_llm: true` in .claude/code-index.yaml
# 2. `code_index.send_code_to_llm: true` in ~/.config/claude-almanac/config.yaml
claude-almanac codeindex arch
```

## Module discovery modes

`modules.from: auto` detects `package.json`/`pnpm-workspace.yaml`/`go.work`/
`Cargo.toml`/`pants.toml` and uses their workspace definitions.

`modules.patterns: [...]` is the explicit alternative; the two are mutually
exclusive.

## Supported languages

| Language | Method | Notes |
|---|---|---|
| Python | stdlib `ast` | `__all__`, underscore visibility, decorators native |
| TS / TSX / JS / JSX | tuned regex | `export` keyword determines visibility |
| Go | tuned regex | Uppercase identifier = public |
| Java | tuned regex | `public` keyword determines visibility |
| Rust / other | Serena HTTP fallback | Requires the Serena daemon on port 51777 |

Rust and other unsupported-by-fast-path languages need a running Serena
server (`serena start-project-server --port 51777`). Serena is NOT bundled
with claude-almanac — if it's unreachable, the fallback extractor returns
empty and indexing continues.

## Trust boundary

`arch` summarization sends source-file content (up to 20 files × 4 KB each per
module) to the Anthropic API via the `claude` CLI. It refuses to run unless
BOTH the repo-local `.claude/code-index.yaml` AND the global `config.yaml`
opt in via `send_code_to_llm: true`. The default in both scopes is `false`.

The `sym` pass never sends source content to any LLM — it only calls the
configured embedder (local by default).

## Performance envelope

Symbol indexing is O(repo). On tested large Python monoliths (17k files)
initial `init` takes 15-25 minutes when scoped correctly. When unscoped over
the entire repo and fallback-heavy, it can take dozens of hours. Lever 1 is
`modules.patterns` to restrict indexing; lever 2 is `extra_excludes` to skip
generated trees.

Arch summaries are lazy — they NEVER run during `init`; users invoke
`claude-almanac codeindex arch` explicitly.

## Auto-inject gate

`core/retrieve.py` appends a `## Relevant code` block to memory hits when:
1. `retrieval.code_autoinject: true` in `config.yaml` (default), AND
2. the prompt contains ≥2 code-signal tokens (backticked identifiers,
   camelCase, file paths, or "how does X work" / "where is X defined" idioms),
   AND
3. a per-repo `code-index.db` exists.

To debug a false-positive gate open/close, run
`python -c "from claude_almanac.codeindex.autoinject import signal_count; print(signal_count('your prompt here'))"`.
