# Roadmap

This roadmap captures where claude-almanac is heading after v0.1. It's a living document — priorities shift based on real usage, contributor bandwidth, and how the broader Claude Code ecosystem evolves.

Sections:

1. [Guiding principles](#guiding-principles) — the constraints that shape every decision
2. [v0.2 — stabilise](#v02--stabilise) — polish + parity with our own v0.1 promises
3. [v0.3 — competitor feature parity](#v03--competitor-feature-parity) — close gaps against the memory-plugin landscape
4. [v0.4 — plugin system](#v04--plugin-system) — first-class extension API so third parties can ship sources, collectors, retrievers
5. [v0.5 and beyond](#v05-and-beyond) — differentiators, team features, cloud variants
6. [Non-goals](#non-goals) — what we deliberately won't build
7. [How to propose changes](#how-to-propose-changes)

---

## Guiding principles

These are the axes every roadmap item is evaluated against. A proposal that violates one of these without a compelling reason doesn't ship.

- **Local-first, opt-in cloud.** All memory + code-index + digest state lives on the user's machine by default. Anything that sends data to Anthropic (the `arch` LLM pass, deep-mode Q&A) must be explicitly enabled per-scope. Team/cloud features in v0.5+ are opt-in, self-hostable, and never required.
- **One install, no orchestration burden.** A user should be able to `uv tool install claude-almanac && /plugin install claude-almanac@claude-almanac && claude-almanac setup` and have the whole system running. We do not ask users to compose services, wire pipelines, or learn our internals.
- **Hooks are the runtime, not a layer.** UserPromptSubmit + Stop are how claude-almanac participates in every session. We optimise for hook speed, hook resilience, and hook failure being graceful (never blocking the user's turn).
- **Trust boundaries are explicit, default-off.** Anything that sends source code or documents to a third party requires a dual flag (global + per-scope). Default is always `false`. We fail loud on mismatch; we never silently migrate or auto-upgrade trust scopes.
- **Pluggable, not prescriptive.** The embedder, the platform scheduler, the Q&A tools, and (in v0.4) the ingestion + retrieval layers are all extension points. We ship solid defaults; we don't lock users into them.
- **Tests pin behaviour, not implementation.** Calibrated thresholds (17.0 dedup for bge-m3), trust-boundary gates, and retrieval contracts are unit-tested. Refactoring that breaks the contract fails CI.

---

## v0.2 — stabilise

**Goal:** close the "known follow-up work" items from the Plan 1-4 specs and harden the v0.1 surfaces against the first real-world usage patterns. No new user-visible features beyond what v0.1 already promised; this is the polish release.

### Commitments

- [x] **Recall pin/unpin/forget/export** — shipped in 0.2.0. Pin/unpin flip `entries.pinned` across both scopes by row-id or slug. `forget` moves md to `<scope>/trash/<slug>.<ts>` and drops archive rows (requires `--scope` on cross-scope slug collisions). `export` concatenates `# scope/slug` blocks; `--global`, `--project`, `--all` scope flags.
- [x] **Curator transcript port completeness** — verified + extended in 0.2.0. Tool-use, multi-part, interrupted turns already worked; compaction (`{"type": "summary"}`) and `subagent_stop` events now surface as their own pseudo-turn types instead of being silently dropped.
- [x] **`/almanac status` richer output** — shipped in 0.2.0. Archive counts (total + pinned per scope), last digest mtime, launchd/systemd unit status for digest/server/codeindex-refresh, Ollama reachability probe, and `EmbedderMismatch` warnings.
- [x] **Integration tests in CI** — shipped in 0.2.0. Three smoke tests (retrieve↔curate↔recall, codeindex init→search, digest generate→serve) run against live Ollama on every PR targeting `release/*`, and `release.yml::publish` now `needs: [build, integration]` so PyPI cannot ship a broken integration gate.
- [x] **Calibration harness CLI wrapper** — shipped in 0.2.0 as `claude-almanac calibrate <provider> <model> <fixture.jsonl>` with histogram + `max × 1.2` threshold suggestion. `add-embedder` skill now points here instead of the `python -m` entrypoint.
- [x] **Observability aggregator** — shipped in 0.2.0 as `claude-almanac tail`. Interleaves the four known log files with `[source ts]` prefixes and continuation-line labelling; `--follow/--no-follow`, `--lines`, `--since`, `--source` flags.
- [x] **Refresh daemon for code-index** — shipped earlier in 0.1.2 via the `code_index.daily_refresh` setup wiring.
- [ ] **Windows support** — deferred to v0.3+. Nothing in 0.2.0 blocks it; contributors welcome.

### Success criteria

- All four Plan 1-4 "Known follow-up work" sections are either closed or explicitly rescoped here.
- A new user can `claude-almanac setup` → add a repo to `digest.repos` → see their first digest the next morning without reading any docs beyond the README.
- CI runs integration tests against live Ollama on every push to `main`.

---

## v0.3 — competitor feature parity

**Goal:** close the gaps against the most-adopted memory plugins for Claude Code (claude-mem, total-recall, mnemex/CortexGraph, claude-memory-compiler, joseairosa/recall, supermemoryai/claude-supermemory). Each item here is directly traceable to a competitor feature; we pick the ones that **compose with our existing architecture** rather than replacing it.

These four land together because they share infrastructure (knowledge graph tables, temporal scoring logic, versioning). Shipping them piecemeal would re-do the DB migration work repeatedly.

### 3.1 — Session-transcript compression layer

**Why:** claude-mem (46K ★) is the most-adopted Claude Code memory plugin. Its distinguishing behaviour is compressing entire session transcripts via the Claude Agent SDK and injecting distilled context into future sessions. Our curator writes individual memory files from each session; the session-level rollup is a *complement*, not a replacement.

**Design sketch:**
- New archive table `session_rollups`: `id`, `session_id`, `started_at`, `ended_at`, `summary_text`, `embedding`, `tool_use_count`, `file_touches[]`.
- Curator extension: after writing per-turn memories, Haiku also produces a ~200-word session summary and stores it here.
- Retrieve hook: when auto-injecting, include the top-1 session rollup if it scores within the same distance band as the memory hits.
- User-facing: `/recall sessions` lists recent rollups, `/recall session <id>` shows the full summary.

**Estimated effort:** 3–5 days. Bulk is the curator prompt iteration + calibrating which session-level signal is actually useful.

### 3.2 — Temporal decay scoring

**Why:** mnemex (now CortexGraph) implements Ebbinghaus-curve-based memory scoring: `score(t) = use_count^β · e^(-λ·Δt) · strength`. Memories naturally fade unless reinforced. Our current model uses a binary 180-day prune. Temporal decay gives retrieval a smoother notion of "what still matters."

**Design sketch:**
- Add columns to `entries`: `last_used_at`, `use_count` (already have `created_at`, `pinned`).
- Retrieve hook: when a memory is returned, increment `use_count` and set `last_used_at = now`.
- Scoring function applied to archive search: blend `distance` with `decay_score(created_at, last_used_at, use_count)`. Formula + parameters live in config so they can be tuned per user.
- Prune replaces binary cutoff with decay-threshold cutoff (default `score < 0.05`).

**Estimated effort:** 2–3 days. Schema migration + scoring function + 1 week of logging decay values to calibrate defaults before enabling.

### 3.3 — Knowledge-graph edges

**Why:** mnemex/CortexGraph and the official MCP `server-memory` plugin both support explicit relations between memories (e.g., `supersedes`, `referenced-by`, `part-of`). This enables multi-hop queries like "why did we decide X, and what changed afterward?" which our pure semantic search can't answer.

**Design sketch:**
- New archive table `edges`: `(from_entry_id, to_entry_id, relation, created_at, metadata_json)`.
- Curator extension: when writing a new memory, optionally emit `supersedes` / `references` edges to existing slugs. Haiku decides based on the conversation tail.
- `/recall show <slug> --graph` renders the local neighbourhood (direct edges, one hop out).
- Retrieve hook: when top hits include a node with heavy edge fan-out, surface 1–2 related nodes as "see also."

**Estimated effort:** 4–6 days. Schema + curator prompt + CLI + retrieve integration.

### 3.4 — Write gates + correction propagation + memory versioning

**Why:** total-recall's differentiator is that memories are editable and corrections propagate — you can supersede a memory, and retrieval knows to prefer the newer version while still making the old visible under `/recall history`. Our model silently overwrites via dedup redirect, which loses the audit trail.

**Design sketch:**
- New archive table `entries_history`: stores every version of each entry with `version`, `superseded_at`, `supersedes_entry_id`.
- Curator extension: when dedup redirect fires, the old body is copied to `entries_history` before overwrite.
- `/recall correct <slug> "<new body>"` explicit user-facing supersede; `/recall history <slug>` shows versions.
- Retrieve hook: by default returns only current versions; `--include-history` flag surfaces past versions.
- Trust: corrections are append-only. There is no destructive "rewrite history" path in the CLI.

**Estimated effort:** 3–5 days.

### 3.5 — Deferred to v0.4 or later (not in v0.3 scope)

- **Knowledge-article compiler** (claude-memory-compiler's Karpathy-style KB): the validation story is genuinely hard (LLM-generated articles with no ground truth). Defer until we've shipped 3.1–3.4 and have real usage data to inform whether articles actually help retrieval more than raw memories do.
- **Shared/team memory backend** (joseairosa/recall's Redis/Valkey mode): big scope, requires auth + sync + conflict resolution. v0.5+.
- **Mobile/voice capture** (supermemory-style ambient capture): requires a client we don't have. v0.5+.

### Success criteria

- Every competitor-parity claim in the README is now true for claude-almanac. We can defensibly say "what claude-mem does, plus code-index, plus daily digest, plus local-first."
- A user migrating from another memory plugin can import their markdown files into our `global/` dir and have feature parity within one release cycle.

---

## v0.4 — plugin system

**Goal:** Introduce a first-class extension API so third parties (and we ourselves) can ship **sources**, **collectors**, **retrievers**, and **commands** without modifying the core package. The canonical motivating use case is the user's own example: **document drag** — drop a PDF into a watched directory and have it become searchable memory.

### Why a plugin system (vs. forks or PRs)

- Forks have a maintenance tax that kills most of them within 6 months.
- PRs into core force us to be the gatekeeper for every integration (Notion, Obsidian, Linear, Jira, Google Drive, etc.). That doesn't scale.
- The ecosystem around Claude Code plugins is already diverse; we should be a substrate others can build on, not a monolith.

### Plugin types

| Type | Purpose | Example |
|---|---|---|
| **Source** | Ingests content into the memory archive via its own trigger (file watch, webhook, polling API). | `claude-almanac-docdrop`: watches `~/Drop/`, ingests dropped PDFs/markdown/text. |
| **Collector** | Contributes items to the daily digest's collection phase. | `claude-almanac-linear`: pulls closed Linear issues in the 24h window. |
| **Retriever** | Provides additional hits during the UserPromptSubmit retrieve phase, alongside the default memory + code-index hits. | `claude-almanac-obsidian`: searches a local Obsidian vault. |
| **Tool** | Registers additional Q&A tools for the digest deep-mode loop (already partially supported; v0.4 formalises the interface). | `claude-almanac-github`: adds `github_pr_show` tool. |

### Discovery and registration

- Plugins are regular Python packages that declare an entry point in the `claude_almanac.plugins` namespace:

  ```toml
  # plugin's pyproject.toml
  [project.entry-points."claude_almanac.plugins"]
  docdrop = "claude_almanac_docdrop:register"
  ```

- At startup, claude-almanac scans this entry-point group, calls each `register(almanac)` function, and the plugin adds itself to the relevant registry (source/collector/retriever/tool).
- Plugins ship as standalone PyPI packages. Install is `pip install claude-almanac-docdrop` inside the uv tool's venv (or `uv tool install` it alongside claude-almanac). No code edits to claude-almanac required.

### Lifecycle hooks

```python
# minimal plugin interface (v0.4 target)

class Plugin(Protocol):
    name: str
    kind: Literal["source", "collector", "retriever", "tool"]

    def on_install(self, ctx: AlmanacContext) -> None:
        """One-time setup: create tables, write config defaults, claim storage."""

    def on_uninstall(self, ctx: AlmanacContext) -> None:
        """Cleanup — nothing should persist after this returns."""

    def health(self, ctx: AlmanacContext) -> HealthReport:
        """Surface plugin status in `claude-almanac status`."""
```

Each plugin type adds its own methods on top:

```python
class Source(Plugin):
    def start(self, ctx: AlmanacContext) -> None:
        """Begin producing events (e.g., start a file watcher)."""

    def stop(self, ctx: AlmanacContext) -> None:
        """Stop producing events."""

    # The source calls ctx.archive.insert_entry(...) to ingest.

class Collector(Plugin):
    def collect(self, ctx: AlmanacContext, window: TimeWindow) -> list[DigestItem]:
        """Return items for the daily digest."""

class Retriever(Plugin):
    def retrieve(self, ctx: AlmanacContext, query: str, top_k: int) -> list[Hit]:
        """Return hits to merge with memory + code-index results."""

class Tool(Plugin):
    def register_tools(self, registry: ToolRegistry) -> None:
        """Register @tool-decorated functions for the deep-mode QA loop."""
```

### `AlmanacContext` — shared primitives

The context object exposes vetted APIs into the core; plugins never import internal modules directly:

```python
class AlmanacContext:
    archive: ArchiveAPI       # insert_entry, search, prune (read-only for non-Sources)
    embedder: Embedder        # embed(texts) — same one the core uses, metadata-guarded
    paths: PathsAPI           # plugin_data_dir(name), plugin_config_file(name)
    config: PluginConfigAPI   # typed get/set scoped to this plugin's namespace
    logger: Logger            # structured log emitter (routes into code-index.log-style format)
```

This gives us a clean surface to version. Plugins declare `claude-almanac >= 0.4, < 0.5` and we can break internals freely across minor versions without breaking plugins.

### Canonical example: `claude-almanac-docdrop`

User drops a PDF into `~/Drop/`. The plugin:

1. On `start()`: spawns an `inotify` (Linux) or `fsevents` (macOS) watcher on the configured directory.
2. On file-created event: detects mime type, extracts text (PDF via `pypdf`, docx via `python-docx`, markdown/txt via direct read), chunks it with semantic boundaries, embeds each chunk, inserts into the archive with `source="drop:<filename>"` and `kind="document"`.
3. `/recall search "the thing from that PDF"` now returns those chunks alongside regular memories.
4. The file can optionally be moved to `~/Drop/.processed/` after ingestion so the same drop doesn't re-fire.

Configuration via `~/.config/claude-almanac/plugins/docdrop.yaml`:

```yaml
watch_dir: ~/Drop
processed_dir: ~/Drop/.processed
extensions: [.pdf, .md, .txt, .docx, .epub]
max_file_size_mb: 50
chunk_strategy: semantic  # or "fixed_tokens"
chunk_size: 800
```

### Other plugins we expect to ship from core

To dogfood the plugin API and ensure the surface is actually usable, v0.4 also ships 2-3 "first-party" plugins built on it:

- `claude-almanac-obsidian` (retriever): searches an Obsidian vault.
- `claude-almanac-linear` (collector): pulls Linear closed-this-window into the digest.
- `claude-almanac-github` (tool): adds `github_pr_show` to deep-mode Q&A.

These also serve as the reference implementations in `docs/plugin-authoring.md`.

### Plugin safety

- Plugins run in-process (same Python interpreter as the hooks). There is no sandbox. Users are trusted to audit plugins before installing — the same trust model as any `pip install`.
- The AlmanacContext grants explicit, minimal capabilities. A Collector cannot write to the archive. A Source cannot emit LLM requests.
- Plugins that want to hit LLMs use the user's `claude` CLI via subprocess (same auth story as core). No raw API-key boilerplate.
- `claude-almanac status` lists installed plugins and their declared capabilities so users can audit what's active.

### Success criteria

- Third party can write a useful plugin in under an afternoon using only `docs/plugin-authoring.md`.
- All four plugin types have at least one first-party implementation shipping with the release.
- The `docdrop` plugin ships, documented, with fixtures for PDF/docx/markdown ingestion.

---

## v0.5 and beyond

Longer-horizon items that need more design work or depend on the ecosystem evolving. Listed in rough priority order, not as commitments.

### Team and cloud

- **Shared team memory** (joseairosa/recall pattern). Self-hostable Redis/Valkey backend that mirrors the per-repo archive across team members. Requires auth, conflict resolution, and a selective-sync model (not all memories are team-appropriate).
- **Managed cloud variant.** Optional hosted service that provides the shared backend for users who don't want to run Redis themselves. Sits on top of the self-hostable backend — never the only path.

### Differentiators

- **Memory → PR generator.** Given a memory thread on "we should refactor X because Y," draft an actual PR with the refactor. Uses the code-index for symbol targeting. Opt-in, LLM-heavy.
- **Decision timeline.** Cross-repo visualisation of how a memory evolved over time, with edges from the knowledge graph (v0.3) and versioning (v0.3). Web UI only.
- **Ambient capture.** Browser extension that lets you send the current tab into memory. Voice-note capture via Whisper for walking thoughts.

### Ecosystem

- **MCP server mode.** Expose claude-almanac's retrieve + code-index as an MCP server so non-Claude-Code clients (Cline, Cursor, Zed with MCP, etc.) can consume it.
- **IDE adapters.** Thin VS Code / JetBrains extensions that show the same auto-inject context as Claude Code sees, plus inline `/recall` invocation.
- **Import tools.** First-class importers for the largest competing plugins (claude-mem, total-recall) so users can migrate without losing their history.

---

## Non-goals

These are deliberately out of scope. Proposals to add them will be closed with a pointer to this section.

- **Replacing Ollama with a bundled embedder.** We stay BYO-embedder. The default is Ollama because it's local and high-quality; we support OpenAI and Voyage for users who want cloud. Shipping our own embedder inflates binary size and creates a model-maintenance burden we don't want.
- **Server-side LLM calls.** All LLM calls go through the user's local `claude` CLI. We never ship claude-almanac with its own API key embedded, never proxy through a cloud we operate, never require `ANTHROPIC_API_KEY` as an env var. If Anthropic changes the CLI's auth model, we adapt; we don't work around it by bringing our own.
- **Automatic code changes.** claude-almanac retrieves, summarises, and indexes. It does not write code on the user's behalf. That belongs in other plugins/tools.
- **Closed-source plugins in core.** Every first-party plugin ships MIT or BSD. Third parties are free to ship whatever license they want, but we don't link or recommend closed-source from our docs.
- **Replacing Claude Code's skill system.** Our bundled skills (`recall`, `digest`) are thin triggers — they call our slash commands. We don't re-implement skill discovery, skill composition, or skill authoring inside claude-almanac. That's Claude Code's job.

---

## How to propose changes

- Small stuff (typos, bug-fix prioritisation, clarifications): open a GitHub issue or PR.
- New roadmap item: open a GitHub issue with `[roadmap]` in the title, describing:
  1. The user problem (who is this for? what are they trying to do?)
  2. Why claude-almanac, vs. a separate tool or a different plugin?
  3. Rough scope (hours/days/weeks).
  4. Which principle(s) from "Guiding principles" it supports or risks violating.
- Plugin ideas: you don't need our permission. Start from `docs/plugin-authoring.md` (ships with v0.4) and build. If it's useful, we'll link it from here.
- Architectural shifts (v0.5+ items above, or entirely new directions): open an issue labeled `[discussion]` so we can talk before code happens.

This file is updated as milestones land. Use the git history on `ROADMAP.md` to see how priorities have moved.
