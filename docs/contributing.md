# Contributing

Thanks for your interest. This doc covers dev setup, extension points (embedders + platform adapters), test conventions, and the maintainer release process.

## Dev setup

```bash
git clone https://github.com/sammctaggart/claude-almanac.git
cd claude-almanac

# Editable install with ALL dev extras
pip install -e '.[dev,openai,voyage]'

# Or with uv
uv pip install -e '.[dev,openai,voyage]'

# Verify
ruff check .
mypy src/claude_almanac
pytest tests/unit -v
```

Integration tests require a live Ollama:

```bash
ollama serve &
ollama pull bge-m3
pytest -m integration -v
```

## Project layout

See [architecture.md](architecture.md) for the system map. High level:

- `src/claude_almanac/core/` — archive DB, retrieve, curator, paths, config
- `src/claude_almanac/embedders/` — pluggable embedder adapters (ollama, openai, voyage)
- `src/claude_almanac/codeindex/` — per-repo symbol + arch index
- `src/claude_almanac/digest/` — daily generator, FastAPI server, Q&A tools
- `src/claude_almanac/platform/` — macOS launchd + Linux systemd
- `src/claude_almanac/cli/` — `claude-almanac <subcommand>` entrypoints
- `src/claude_almanac/hooks/` — `UserPromptSubmit` + `Stop` hook handlers

## Extension: adding an embedder adapter

Embedders implement the `Embedder` protocol in `src/claude_almanac/embedders/base.py`:

```python
class Embedder(Protocol):
    name: str                                # "ollama", "openai", "voyage", ...
    dim: int                                 # vector dimension
    distance: Literal["l2", "cosine"]        # sqlite-vec metric
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

### Steps

1. **Create the adapter file** — `src/claude_almanac/embedders/<provider>.py`. Use `httpx` for REST providers; use the vendor SDK if one exists. Handle timeouts, rate limits, and 5xx errors (return a clear exception; don't silently retry).

2. **Register in the factory** — edit `src/claude_almanac/embedders/__init__.py` to add a branch in `make_embedder(provider, model)`. Import lazily to keep optional deps optional.

3. **Write the profile** — add `(provider, model)` → profile entries in `src/claude_almanac/embedders/profiles.py`. You MUST run the calibration harness before shipping a profile:

   ```bash
   claude-almanac calibrate --provider <name> --model <model> \
     --corpus tests/fixtures/calibration_corpus.jsonl
   ```

   Paste the resulting histogram + suggested threshold into the PR description. Profiles without measured thresholds are not mergeable.

4. **Add unit tests** — `tests/unit/test_embedders_<provider>.py`. Use `respx` (for httpx) or `unittest.mock` to stub the HTTP/SDK calls. Test the happy path, auth error, rate limit, and dim mismatch.

5. **Add an integration test (optional but encouraged)** — `tests/integration/test_embedders_<provider>_live.py`, marked `@pytest.mark.integration` and skipped if the relevant API key env var isn't set.

6. **Update docs** — `docs/config.md` profile table; `docs/install.md` install section if install instructions differ from OpenAI/Voyage.

7. **Extras in `pyproject.toml`** — add an optional dep group `[project.optional-dependencies].<provider>` for the vendor SDK.

## Extension: adding a platform adapter

Platform adapters implement `Scheduler` and `Notifier` protocols in `src/claude_almanac/platform/base.py`. The current shipped adapters are `macos_launchd.py` and `linux_systemd.py`.

### Steps

1. **Create the adapter file** — `src/claude_almanac/platform/<name>.py`, implementing both `Scheduler` and `Notifier` for the target OS.

2. **Register auto-detection** — edit `src/claude_almanac/platform/__init__.py` to add a branch in `get_scheduler()` keyed on `platform.system()`.

3. **Render unit files from templates** — put Jinja templates in `src/claude_almanac/platform/templates/<name>/` and render into the OS-appropriate location (e.g. `~/Library/LaunchAgents/` on macOS, `~/.config/systemd/user/` on Linux).

4. **Write golden-file tests** — `tests/unit/test_<name>.py`. Render each template with fixed inputs and diff against a checked-in golden file under `tests/unit/golden/platform/<name>/`.

5. **Test the notifier** — a simple `notify(title, message, link=None)` should be exercised with a subprocess mock.

6. **Update `docs/install.md`** — add a per-platform install section.

## Test conventions

### TDD expectation

All new code lands with tests in the same PR. For branching logic with calibrated thresholds (dedup, arch gates, auto-inject gate), write the test first — red → green → refactor. For pure plumbing (I/O, subprocess calls, template rendering), write the implementation alongside a mock-based unit test.

### Mock-for-logic + integration-for-plumbing

Per the validated strategy in the spec:

- **Unit (`tests/unit/`)** — branching logic, calibrated thresholds, embedder adapters with mocked HTTP, path resolver against tmp-path env overrides, platform-unit renderers against golden files. Run by default.
- **Integration (`tests/integration/`)** — embed → archive → sqlite pipeline, curator round-trip, digest generator end-to-end, Q&A endpoints. Requires live Ollama. Marked `@pytest.mark.integration`; skipped by default (`addopts = "-m 'not integration'"` in pyproject.toml).

### Running the full suite

```bash
# Unit only (fast, default)
pytest tests/unit

# Integration (requires ollama + bge-m3)
pytest -m integration

# Both
pytest tests/ -v
```

### Coverage

```bash
pytest tests/unit --cov=src/claude_almanac --cov-report=term-missing
```

CI enforces unit + ruff + mypy on every PR. Integration runs on `main` pushes only (see `.github/workflows/ci.yml`).

## Release process (maintainers only)

1. Ensure `main` is green (unit, ruff, mypy, and the integration job on `main`).
2. Pre-release smoke test on a clean machine — see the checklist in [release-smoke-test](#pre-release-smoke-test).
3. Bump `version` in `pyproject.toml` AND in `plugin.json`. Both values must match.
4. Update `CHANGELOG.md` with the new version section (see the `Keep a Changelog` format we use).
5. Commit: `git commit -m "chore(release): v0.1.0"`.
6. Tag and push: `git tag -a v0.1.0 -m "v0.1.0" && git push origin main v0.1.0`.
7. The `release.yml` workflow fires on the `v*` tag, builds the wheel + sdist, runs `twine check`, and publishes to PyPI via the trusted-publisher flow.
8. Create a GitHub Release from the tag with the CHANGELOG section as the body. Attach the wheel + sdist (optional; PyPI has them).
9. Update the Claude Code plugin marketplace listing — see [marketplace-submission](#marketplace-submission) below.

### Pre-release smoke test

On a clean VM or a fresh user account (not the dev machine):

```bash
# Install Ollama + bge-m3
brew install ollama && brew services start ollama && ollama pull bge-m3
# Install Claude Code (follow its docs)
/plugin install claude-almanac
claude-almanac setup
# Inside Claude Code
/recall search "test"               # should return "no hits" cleanly
/recall code "some function"        # should say "no code-index.db" cleanly
# Trigger a Stop hook by ending a turn, then check:
tail -n 50 "$(claude-almanac path data)/logs/curator.log"
# Enable digest, re-run setup, wait for the hour
```

Document any rough edges in a GitHub issue against the release candidate.

### Marketplace submission

The Claude Code plugin marketplace expects `plugin.json` to have:

```json
{
  "name": "claude-almanac",
  "version": "0.1.0",
  "description": "Daily intelligence layer for Claude Code",
  "hooks": "./hooks/hooks.json",
  "commands": "./commands/",
  "skills": "./skills/",
  "keywords": ["memory", "digest", "code-index", "retrieval", "claude-code"],
  "repository": "https://github.com/sammctaggart/claude-almanac",
  "license": "MIT",
  "author": "Sam McTaggart"
}
```

Submission is via the marketplace maintainer's PR process (check the current docs at the Claude Code plugin marketplace repository). Include a short description (≤280 chars), 2–3 screenshots (digest UI, `/recall` output, and the Claude Code command palette showing `/recall`/`/digest`/`/almanac`), and link to the GitHub release.

## Coding conventions

- **Python 3.11+**, no backports.
- **`ruff`** for linting (config in `pyproject.toml`). `ruff format` is NOT required; we use the default Python style via `ruff`'s formatter.
- **`mypy --strict`** on `src/`. Tests may use looser typing where mocking makes strict typing painful.
- **Type hints everywhere.** `from __future__ import annotations` at the top of every file.
- **Logging via `logging`**, not `print`, in library code. CLI entrypoints print to stdout for human consumption.
- **No global state** except process-level singletons explicitly justified (e.g. the platform scheduler is a singleton).

## Filing issues

- Bug reports: include OS, Python version, `claude-almanac --version`, and the relevant log tail from `logs/curator.log`, `logs/digest.log`, or `logs/server.log`.
- Feature requests: link to the brainstorming memo or the open question in the spec. We triage with competitor-feature parity in mind (see `project_competitor_features_v2_backlog`).
- Embedder compatibility issues: include the output of `claude-almanac embedder probe` and the full calibration histogram if you ran the harness.
