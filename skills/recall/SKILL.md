---
name: recall
description: Search past decisions, prior discussions, and project-specific context saved by claude-almanac. Use when the user references earlier work ("what did we decide about X", "why is Y the way it is", "we talked about Z before") or uses an unfamiliar project acronym/term that warrants a memory lookup before guessing.
---

# recall

claude-almanac maintains a semantic archive of past sessions plus curated markdown memory files, scoped per-repo (worktree-safe) and globally. The `/recall` command exposes search, listing, and code-index retrieval over that archive.

## When to trigger

Invoke `/recall search <rephrased keywords>` **before answering** when any of these apply:

- The user references earlier work by tense or deixis: "what did we decide about", "why is X the way it is", "we talked about Y before", "remember when", "last time we".
- The user names a project-specific acronym or concept you don't recognize. A directed recall often saves a speculation round-trip.
- Auto-injected `## Relevant memories` appears at the top of the turn but reads topically adjacent rather than on-point. Treat the auto-inject as a hint, not authoritative — a directed search confirms whether the gap is a retrieval miss or a content mismatch.

For cross-repo lookups (a concept defined in one repo but referenced from another), use `/recall search-all <query>` instead.

## Code questions

If the user's prompt mentions a specific symbol name, file path, module, or "how does X work / where is X defined" idiom, prefer `/recall code <query>`. This bypasses the auto-inject gate and hits the per-repo code index directly, returning symbol + arch summaries rather than memory entries. Requires `claude-almanac codeindex init` to have been run for the repo.

**Query phrasing matters.** The code index retrieves via vector similarity using a small embedder (qwen3-embedding:0.6b by default). Single-word or terse queries embed close to the centroid and let generic test/helper symbols out-rank domain-specific ones. Phrase `recall code` queries as **3–5 word natural-language descriptions** — include kind, domain, and a distinctive token:

- ❌ `recall code "tui"` → ranks unrelated tests high
- ✅ `recall code "TUI terminal report Model"` → surfaces `tuireport/model.go::Model` directly
- ❌ `recall code "segmentation"` → ranks prompt constants high
- ✅ `recall code "audience segment builder"` → surfaces the segmentation service module
- ❌ `recall code "flow"` (might work, might not)
- ✅ `recall code "flow publish modal hook"` → surfaces the specific hook module

If the first query is noisy, don't give up — add a distinguishing noun (module name, behaviour verb, or architectural kind) and retry. The index is usually correct; retrieval ranking is the weak link.

## Anti-triggers

Do NOT use `/recall` for:

- Open-ended exploration of current code state. Grep, Glob, or Serena is faster and authoritative.
- Single-commit lookups — `git show <sha>` is cheaper and direct.
- "Is this still true?" checks about code behavior — read the file; the archive is a hint, the source is the truth.

## How to use the result

Recall hits are advisory context. Quote them when useful but verify against current code before citing them as facts. If a hit contradicts the current codebase, the code wins and the memory should be flagged as stale (the user can `/recall forget` it in a future session).
