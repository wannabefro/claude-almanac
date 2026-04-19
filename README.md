# claude-almanac

A daily intelligence layer for Claude Code — remembers what you've done, summarizes what changed, and surfaces it when you need it.

## Quickstart

```bash
# 1. Install the Claude Code plugin
/plugin install claude-almanac

# 2. Run first-time setup
claude-almanac setup

# 3. Use recall
/recall search "authentication"
```

## Features

- **Self-curating memory**: an LLM picks what's worth remembering from each session and writes structured markdown.
- **Pluggable embeddings**: Ollama (default, local), OpenAI, or Voyage.
- **Per-repo scoping**: memory is scoped to a git repo (worktree-safe via git-common-dir).
- **XDG-compliant storage**: no files in your home dir; respects `$XDG_DATA_HOME` / macOS conventions.
- **Cross-platform**: macOS (launchd) and Linux (systemd).

## Documentation

- [Install](docs/install.md)
- [Config reference](docs/config.md)
- [Contributing](docs/contributing.md)
- [Architecture](docs/architecture.md)

## License

MIT
