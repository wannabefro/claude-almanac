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

### Deferred in v0.1

`pin`, `unpin`, `forget`, and `export` are tracked for v0.2. Invoking them
prints a clear "not implemented" message with a link to the issue tracker.
