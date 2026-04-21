---
description: Search and manage long-term memories (by-repo + cross-repo)
argument-hint: "<search|search-all|list|show|code> [args]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/recall:*)
---

Run the memory recall tool with the provided arguments and present the output verbatim.

Execute:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/recall $ARGUMENTS
```

If `$ARGUMENTS` is empty, show the usage help.

### `recall code <query>`

Search the per-repo code index directly. Returns symbol + module summaries.
Requires `claude-almanac codeindex init` to have run for this repo.

Example:
  recall code "jwt verification flow"

Note: code-index hits are also auto-injected alongside memory hits for prompts
that look like code questions (the `autoinject.should_query` gate in
`core/retrieve.py`). Use `recall code <query>` when you want to bypass the gate
and search the index directly.

### `recall link <slug-a> <slug-b>`

Create a symmetric `related` edge between two memory slugs. Both directions
are inserted. Slugs are the bare filename (without the `.md` extension) as
stored in the archive's `source` field.

### `recall supersede <new-slug> <old-slug>`

Mark `new-slug` as superseding `old-slug`. Inserts a one-directional
`supersedes` edge (new → old). Use this when a memory has been replaced by a
newer one so retrieve can skip the stale version.

### `recall unlink <slug-a> <slug-b> [--type TYPE]`

Remove edge(s) between two slugs. For `related` edges both directions are
removed. For other types only the specified direction (a → b) is removed.
Defaults to `--type related`.

### `recall links <slug>`

Show all incoming and outgoing edges for a slug. Prints two sections:
`Outgoing` (→) and `Incoming` (←) with edge type and creator.

### `recall rollups <query>`

Semantic search over session rollups. Returns the top-k rollups ranked by
embedding distance, showing the rollup id, distance, and narrative excerpt.
Uses the same embedder configured in `~/.config/claude-almanac/config.yaml`.

### `recall rollup-now`

Manually trigger a rollup for the most recent transcript in the current
repo's Claude project directory. Invokes the rollup runner subprocess with
`--trigger explicit`. Requires that Claude Code has already written at least
one transcript for this working directory.
