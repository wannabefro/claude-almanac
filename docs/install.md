# Install

claude-almanac is a Claude Code plugin plus an installable Python package. The plugin is discovered via Claude Code's plugin marketplace; the package is installed by `claude-almanac setup` the first time you run it.

## Prerequisites

- Claude Code (latest)
- Python 3.11 or newer
- macOS 14+ or Linux with systemd user session enabled
- Ollama (for the default local embedder) — or an OpenAI / Voyage API key if you prefer cloud embedders
- `git` on `$PATH` (used by the digest commit collector and by the git-common-dir key derivation)

## 1. Install Ollama (default local embedder)

### macOS

```bash
brew install ollama
brew services start ollama
ollama pull bge-m3
```

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
systemctl --user enable --now ollama   # or: sudo systemctl enable --now ollama
ollama pull bge-m3
```

Verify:

```bash
ollama list | grep bge-m3
curl -s http://127.0.0.1:11434/api/tags | grep bge-m3
```

If you prefer a cloud embedder, skip this step — see "Cloud embedders" below.

## 2. Install the Claude Code plugin

Inside a Claude Code session:

```
/plugin install claude-almanac
```

Claude Code caches the plugin, reads `plugin.json`, and registers the `/recall`, `/digest`, and `/almanac` commands plus the `UserPromptSubmit` + `Stop` hooks. The first hook fire detects the uninitialized state and prints:

```
claude-almanac installed but not set up. Run `claude-almanac setup`.
```

## 3. Run first-time setup

From any shell (inside or outside Claude Code):

```bash
claude-almanac setup
```

This command is idempotent. It:

1. Runs `uv tool install` (or falls back to `pip install`) of the `claude_almanac` Python package from `${CLAUDE_PLUGIN_ROOT}/src/`.
2. Creates the data directory at `~/Library/Application Support/claude-almanac/` (macOS) or `$XDG_DATA_HOME/claude-almanac/` (Linux) and writes empty DBs.
3. Writes a default `config.yaml` to `~/.config/claude-almanac/config.yaml` if one doesn't exist.
4. Detects the current OS and installs platform units (launchd plist on macOS; systemd `--user` service + timer on Linux) — but only if `digest.enabled: true` in config, which it is NOT by default.
5. Probes the configured embedder and reports reachability.

Verify:

```bash
claude-almanac setup                  # re-run: should say "setup complete" on subsequent runs
claude-almanac digest status          # if digest.enabled=true
/recall search "test query"           # inside Claude Code — should return 0 hits without erroring
```

## 4. Enable the digest (optional)

The digest is off by default so first-run doesn't install background jobs you didn't ask for. To enable:

```bash
$EDITOR ~/.config/claude-almanac/config.yaml
```

Set `digest.enabled: true` and add one or more repos:

```yaml
digest:
  enabled: true
  hour: 7            # 7 AM local time
  notify: true
  repos:
    - path: ~/code/myrepo
      alias: myrepo
```

Then re-run `claude-almanac setup`. The launchd/systemd units will be installed and will fire at the configured hour.

## Cloud embedders (optional)

Instead of Ollama, claude-almanac can embed via OpenAI or Voyage. Install the optional extras and configure:

```bash
pip install 'claude-almanac[openai]'
# or
pip install 'claude-almanac[voyage]'
```

In `~/.config/claude-almanac/config.yaml`:

```yaml
embedder:
  provider: openai        # or: voyage
  model: text-embedding-3-small
  api_key_env: OPENAI_API_KEY
```

Set the matching API key env var and re-run `claude-almanac setup` to probe reachability. **Switching embedders requires re-indexing** (archive, code-index, and activity DBs each store the embedder name and dim — mismatched reads fail loudly rather than silently corrupting). Re-indexing means `rm` of the `.db` files and letting the system repopulate; see [docs/config.md](config.md) for the full procedure.

## Relocating data

Both directories are overridable via env var:

```bash
export CLAUDE_ALMANAC_DATA_DIR=~/some/custom/data
export CLAUDE_ALMANAC_CONFIG_DIR=~/some/custom/config
claude-almanac setup
```

Setting these globally (e.g. in `~/.zshrc`) also affects the background launchd/systemd units after a `claude-almanac setup` re-run, since those units capture the env vars at install time.

## Uninstall

```bash
claude-almanac setup --uninstall          # removes platform units, leaves data
claude-almanac setup --purge-data         # removes platform units AND wipes data (confirmed prompt)
```

To also uninstall the Python package:

```bash
uv tool uninstall claude-almanac     # or: pip uninstall claude-almanac
```

And to remove the Claude Code plugin, use Claude Code's plugin manager UI.

## Troubleshooting

### "embedder unreachable" during setup

- Ollama: `curl -s http://127.0.0.1:11434/api/tags` — if this fails, Ollama isn't running. Start it with `brew services start ollama` (macOS) or `systemctl --user start ollama` (Linux).
- OpenAI/Voyage: verify the API key env var is set in the shell where you ran `claude-almanac setup`.

### The Stop hook isn't saving memories

- Check `~/Library/Application Support/claude-almanac/logs/curator.log` (macOS) or `$XDG_DATA_HOME/claude-almanac/logs/curator.log` (Linux).
- Verify the `claude` CLI is on `$PATH` (`which claude`). The curator shells out to `claude -p --model haiku`.
- If you see `curator: no conversation tail, skipping` on every Stop, the Stop hook isn't being given a `transcript_path` by Claude Code. File a GitHub issue with your Claude Code version.

### The digest UI is unreachable at 127.0.0.1:8787

- Verify the server unit is running: `launchctl list | grep claude-almanac` (macOS) or `systemctl --user status com.claude-almanac.server` (Linux).
- Check the server log at `~/Library/Application Support/claude-almanac/logs/server.log` for bind errors (port conflict, IPv6 issues).

### Integration tests fail locally

Integration tests require a live Ollama with `bge-m3` pulled. Run:

```bash
pip install -e '.[dev,openai,voyage]'
ollama serve &
ollama pull bge-m3
pytest -m integration
```

See [docs/contributing.md](contributing.md) for the full test matrix.

## Claude Code plugin marketplace submission (for maintainers)

claude-almanac is listed in the Claude Code plugin marketplace. If you're forking and want to publish your fork under a different name:

1. Update `plugin.json` — change `name`, `version`, and `description` to your fork's values.
2. Ensure `keywords` and `repository` fields match the marketplace's schema (see [docs/contributing.md](contributing.md#marketplace-submission) for the current schema).
3. Submit via the marketplace maintainer's channel. Exact submission mechanism is described in the [Claude Code plugin marketplace docs](https://docs.claude.com/claude-code/plugins) (link current as of 2026-04-19).

No action is needed from end-users; `/plugin install claude-almanac` works against the published listing directly.
