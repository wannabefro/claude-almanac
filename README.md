# claude-almanac

**A daily intelligence layer for Claude Code — remembers what you've done, summarizes what changed, and surfaces it when you need it.**

claude-almanac is a Claude Code plugin that adds three tightly-integrated subsystems to your local development environment:

- **Self-curating memory** — an LLM picks what's worth remembering from each session and writes structured markdown, scoped per-repo (worktree-safe) and globally.
- **Daily digest + Q&A** — a background job indexes commits and generates a daily digest per repo, served at `http://127.0.0.1:8787` with a local Q&A endpoint.
- **Code-index retrieval** — a per-repo vector index of public symbols, auto-surfaced alongside memory hits when a prompt looks like a code question.

All three share one pluggable embedder (Ollama by default, OpenAI/Voyage as extras), one XDG-compliant data dir, and one cross-platform install (macOS launchd + Linux systemd).

## What makes it different

- **Positioning is not "memory for LLMs."** The namespace is saturated. claude-almanac leads with daily surfacing — commits, digests, and cross-artifact Q&A — and treats memory as one retrieval source among several.
- **Local-first by default.** Ollama + `bge-m3` + SQLite + local FastAPI server. No cloud dependency in the default path; cloud embedders (OpenAI, Voyage) are opt-in extras.
- **Per-repo worktree-safety.** Memory and code-index databases key off `git-common-dir` so worktrees of the same repo share state without colliding.
- **Trust boundaries are explicit.** The code-index's LLM-powered `arch` summaries refuse to run unless BOTH the repo's `.claude/code-index.yaml` AND the global `config.yaml` opt in via `send_code_to_llm: true`.

## Quickstart (3 steps)

```bash
# 1. Install the Claude Code plugin
/plugin install claude-almanac

# 2. Run first-time setup (creates dirs, writes default config, installs platform units)
claude-almanac setup

# 3. Use it
/recall search "authentication"          # past decisions + context
/digest today                            # today's activity digest (opens browser)
/recall code "jwt verification flow"     # per-repo code-symbol search
```

See [docs/install.md](docs/install.md) for the full per-platform walkthrough, including Ollama install and optional cloud-embedder setup.

## Features

| Subsystem | What it does | Commands |
|---|---|---|
| Memory | Semantic archive of past sessions + curated markdown. Auto-injected at prompt time. | `/recall search`, `/recall search-all`, `/recall list`, `/recall show` |
| Digest | Daily per-repo markdown digests + local Q&A web UI. | `/digest today`, `/digest YYYY-MM-DD`, `/digest generate` |
| Code index | Per-repo vector index of public symbols + optional LLM arch summaries. | `/recall code`, `claude-almanac codeindex init\|refresh\|arch\|status` |

## Supported platforms

| Platform | Status | Scheduler | Notifier |
|---|---|---|---|
| macOS 14+ | supported | launchd | terminal-notifier / osascript |
| Linux (Ubuntu 22.04+, Arch, Fedora) | supported | systemd --user | notify-send |
| Windows | not supported in v0.1 | — | — |

Python 3.11+ required.

## Documentation

- [Install](docs/install.md) — per-platform setup, Ollama install, cloud-embedder setup, troubleshooting
- [Config reference](docs/config.md) — full `config.yaml` schema, env var overrides, embedder profiles
- [Architecture](docs/architecture.md) — system map, hooks flow, where to look to change X
- [Code index](docs/codeindex.md) — per-repo symbol indexing, language support matrix, trust boundary
- [Contributing](docs/contributing.md) — dev setup, adding embedders/platform adapters, test conventions
- [Roadmap](ROADMAP.md) — what's planned for v0.2 → v0.5+ and how the plugin system will work

## License

MIT — see [LICENSE](LICENSE).

## Status

v0.1.0 — first public release. Feedback via [GitHub issues](https://github.com/sammctaggart/claude-almanac/issues). No telemetry.
