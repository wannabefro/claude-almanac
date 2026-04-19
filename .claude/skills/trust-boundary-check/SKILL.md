---
name: trust-boundary-check
description: Verify the dual `send_code_to_llm` trust boundary is honored when changing code-index arch/dispatch/curator code. Use when editing `src/claude_almanac/codeindex/arch.py`, `codeindex/dispatch.py`, `core/curator.py`, or `core/retrieve.py`'s auto-inject branches.
---

# trust-boundary-check

claude-almanac's code-index `arch` pass sends source file content to Anthropic via the `claude` CLI. This is gated by a **dual opt-in flag** — both the repo-local `.claude/code-index.yaml` AND the global `~/.config/claude-almanac/config.yaml` must set `send_code_to_llm: true`. Weakening this gate leaks source.

Invoke this skill when a change touches:

- `src/claude_almanac/codeindex/arch.py` — the arch-pass entrypoint and gate check.
- `src/claude_almanac/codeindex/dispatch.py` — routing between sym and arch passes.
- `src/claude_almanac/core/curator.py` — the curator prompt that LLM-summarizes session transcripts (separate boundary, same discipline).
- `src/claude_almanac/core/retrieve.py` — the auto-inject gate for code hits on `UserPromptSubmit`.

## Check list

1. **Both-flag check is intact.** In `arch.py`, locate the gate (`_should_run_arch` or equivalent). It must read both the repo-local config (via `codeindex/config.py::load_repo_config`) AND the global config (`core/config.py::load_config`), and short-circuit to False if either is absent or False. A single-flag check is a regression.
2. **Default is False in both scopes.** Grep `send_code_to_llm` across the repo and confirm every default is `False`. New config fields added to either file must default to False or the boundary degrades silently for existing users.
3. **Sym pass is isolated.** `codeindex/sym.py` must never call out to the `claude` CLI or pass source content to any embedder API as raw text — it embeds signatures only. If a sym-pass file now imports `arch` or `claude_agent_sdk`, that's a smell worth a second look.
4. **Curator prompt boundary.** `core/curator.py` always sends transcript content to Haiku; that's expected and user-consented at Claude Code install time. But the curator must never pass arbitrary file contents it scraped from the transcript's `cwd` — only the transcript itself.
5. **Auto-inject retrieval.** `core/retrieve.py::build_injection` may query the code-index DB (which contains embeddings, not source). It must not read source files on the fly and inject them. If you see `open(...)` or `Path.read_text()` on a user-repo path inside the retrieve flow, stop and verify why.

## If a finding surfaces

- If the check finds a gate weakening, treat it as a **blocker** — do not commit. Revert the weakening or add the missing flag check.
- If the change is intentional (e.g. a new LLM boundary being introduced deliberately), the PR description must name the new boundary, its default, and the opt-in mechanism. Update `docs/architecture.md::Invariants` and `docs/config.md` in the same PR.
- Invoke the `trust-boundary-reviewer` agent for a focused second pass before commit.

## Anti-triggers

This skill is not useful for:

- Changes to `digest/` code (the digest server runs on localhost and doesn't send source out — different threat model).
- Changes that touch arch.py only for logging, typing, or refactors with no gate-logic change (a quick read is enough; don't bring out the full checklist).
- Sym-only work in `codeindex/sym.py` that doesn't import arch-pass modules.
