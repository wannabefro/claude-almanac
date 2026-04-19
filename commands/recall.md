---
description: Search and manage long-term memories (by-repo + cross-repo)
argument-hint: "<search|search-all|list|show|pin|unpin|forget|export> [args]"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/recall:*)
---

Run the memory recall tool with the provided arguments and present the output verbatim.

Execute:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/recall $ARGUMENTS
```

If `$ARGUMENTS` is empty, show the usage help.
