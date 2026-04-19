---
name: digest
description: Answer activity-shaped questions ("what changed around X", "what happened with Y this week", "show me recent work on Z") using claude-almanac's daily digests and commit history.
---

# digest

claude-almanac generates a daily markdown digest per configured repo, indexes commits into a 30-day activity DB, and exposes a local Q&A endpoint at `http://127.0.0.1:8787/ask` (fast mode, GET) / `/ask/stream` (deep mode, SSE). The `/digest` slash command opens the web UI; for programmatic Q&A inside a conversation, shell out to the endpoint directly.

## When to trigger

Route to the digest Q&A when the user asks an **activity-shaped** question — one whose answer is grounded in commit history, digest summaries, or cross-day patterns rather than the current code:

- "What changed around <feature> recently?"
- "What's happened with <subsystem> this week?"
- "Who worked on <module> and when?"
- "Why was <file> touched so much yesterday?"
- "Summarize the last week of activity on <repo>."

For single-shot browsing, use `/digest today` or `/digest YYYY-MM-DD`. For conversational Q&A, issue a GET against `http://127.0.0.1:8787/ask?q=<url-encoded-question>` and present the answer. Escalate to deep mode (`/ask/stream`) when the user explicitly wants diffs, cross-artifact resolution, or multi-hop reasoning ("show me the diffs", "trace X across repos", "resolve Y between what memory says and what the commits say").

## Anti-triggers

Do NOT use the digest Q&A for:

- **Single-commit lookups.** `git show <sha>` is cheaper and direct.
- **"Is this still true?"** checks. Read the current code; the digest summarizes past activity and can be stale by definition.
- **Current code state.** Grep/Glob/Serena is authoritative for "what does this file do right now"; the digest is about change, not state.
- **Future planning.** The digest is retrospective. For "what should we do next", use the planner agent or the brainstorming skill.

## Fast vs. deep

- **Fast mode (default):** single-hop tool call (memory search, commit search, or `git show`), latency ~1–3s, grounded in top-k retrieval. Use for direct lookups.
- **Deep mode:** multi-hop with resolver + diff tools, latency 10–30s, emits SSE updates. Use only when the user explicitly wants cross-artifact reasoning or full diffs.

Default to fast mode; announce the mode switch before calling deep ("this needs deep mode, will take ~20s").
