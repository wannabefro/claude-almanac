"""Curator worker: invoked via `python -m claude_almanac.core.curator`.

Reads recent conversation state, asks the configured LLM provider what to
save, applies decisions to markdown files + archive DB.

The LLM invocation layer is pluggable via ``make_curator``. Configure the
provider via ``curator.provider`` in ``~/.config/claude-almanac/config.yaml``
(``ollama`` for local gemma3:4b, ``anthropic`` for direct SDK with API key).

The transcript reader parses Claude Code's JSONL session transcript. It
honors ``CLAUDE_ALMANAC_TRANSCRIPT`` (explicit override for CLI/testing)
and ``CLAUDE_ALMANAC_HOOK_TRANSCRIPT`` (set by the Stop hook when forking
the worker).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any

from claude_almanac.curators import make_curator
from claude_almanac.embedders import get_profile, make_embedder

from . import archive, config, dedup, paths, versioning

LOGGER = logging.getLogger("claude_almanac.curator")

MAX_TRANSCRIPT_CHARS = 120_000   # context budget minus prompt overhead


def _setup_logging() -> None:
    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(paths.logs_dir() / "curator.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def _prompt_template() -> str:
    return files("claude_almanac.core.assets").joinpath("curator-prompt.md").read_text()


def _existing_memory_titles() -> str:
    """One-line-per-memory summary of md files across global + current project.

    Fills the ``{{EXISTING_MEMORIES}}`` placeholder in the curator prompt so
    Haiku can route refinements to the existing slug via `update_md` instead
    of coining near-duplicate names.
    """
    lines: list[str] = []
    for label, scope_dir in (
        ("global", paths.global_memory_dir()),
        ("project", paths.project_memory_dir()),
    ):
        if not scope_dir.exists():
            continue
        for md in sorted(scope_dir.glob("*.md")):
            try:
                first = md.read_text().strip().splitlines()[0][:120]
            except OSError:
                first = ""
            lines.append(f"- [{label}] {md.stem}: {first}")
    return "\n".join(lines) if lines else "(none — archive is empty)"


def _build_system_prompt() -> str:
    return _prompt_template().replace("{{EXISTING_MEMORIES}}", _existing_memory_titles())


def _run_llm(conversation_tail: str) -> str:
    """Dispatch to the configured curator provider.

    On any provider-construction or invocation failure, return ``"{}"``
    so ``_parse_decisions`` yields an empty list. Errors are logged.
    """
    try:
        cfg = config.load()
        return make_curator(cfg).invoke(_build_system_prompt(), conversation_tail)
    except Exception as e:
        LOGGER.warning("curator provider unavailable: %s", e)
        return "{}"


def _connect_archive(db: Path) -> sqlite3.Connection:
    """Open a read/write connection to an archive DB with sqlite_vec loaded."""
    import sqlite_vec  # type: ignore[import-untyped]

    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _read_live_text(db: Path, slug: str) -> str | None:
    """Return the current live body text for *slug*, or None if not yet written."""
    if not db.exists():
        return None
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT text FROM entries WHERE source = ?", (f"md:{slug}",)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _emit_edges_after_write(
    *,
    db: Path,
    slug: str,
    new_text: str,
    prior_text: str | None,
    edge_specs: list[dict[str, Any]],
) -> None:
    """Emit supersedes + related edges after a write_md / update_md.

    supersedes: fired automatically when the body changed (prior_text differs from
    new_text). The live entry supersedes the most recent entries_history row for
    that slug.

    related: fired for each ``{"type": "related", "to": <slug>}`` entry in
    *edge_specs*. Unknown target slugs are dropped silently with an INFO log.
    Other edge types from the curator JSON are ignored in v0.3.2.
    """
    body_changed = prior_text is not None and prior_text != new_text
    has_related = any(
        spec.get("type") == "related" and spec.get("to")
        for spec in edge_specs
    )
    if not body_changed and not has_related:
        return

    conn = _connect_archive(db)
    try:
        # Scope is always project-scoped from the curator (global entries live in
        # the global DB; the scope string just reflects the entry's origin DB).
        live_id = archive.lookup_entry_id_by_slug(conn, slug)
        if live_id is None:
            LOGGER.warning("edge-skip: live entry not found for slug %r", slug)
            return

        # Detect scope from the DB path to build the correct scope string.
        scope_str = (
            "entry@global"
            if db.parent == paths.global_memory_dir()
            else "entry@project"
        )

        from claude_almanac.edges.store import insert_edge

        # --- supersedes edge ---
        if body_changed:
            hist_row = conn.execute(
                "SELECT id FROM entries_history WHERE slug = ? "
                "ORDER BY version DESC LIMIT 1",
                (slug,),
            ).fetchone()
            if hist_row is not None:
                history_id = int(hist_row[0])
                insert_edge(
                    conn,
                    src_id=live_id, src_scope=scope_str,
                    dst_id=history_id, dst_scope=scope_str,
                    type="supersedes", created_by="curator",
                )
                LOGGER.info(
                    "edge: %r (entry %d) supersedes history row %d",
                    slug, live_id, history_id,
                )

        # --- related edges from curator JSON ---
        for spec in edge_specs:
            if spec.get("type") != "related":
                continue  # only 'related' allowed from curator JSON in v0.3.2
            target_slug = spec.get("to")
            if not target_slug:
                continue
            target_id = archive.lookup_entry_id_by_slug(conn, target_slug)
            if target_id is None:
                LOGGER.info("edge-drop: unknown target slug %r", target_slug)
                continue
            insert_edge(
                conn,
                src_id=live_id, src_scope=scope_str,
                dst_id=target_id, dst_scope=scope_str,
                type="related", created_by="curator",
            )
            LOGGER.info(
                "edge: %r (entry %d) related -> %r (entry %d)",
                slug, live_id, target_slug, target_id,
            )
    finally:
        conn.close()


def _apply_decisions(decisions: list[dict[str, Any]]) -> None:
    cfg = config.load()
    profile = get_profile(cfg.embedder.provider, cfg.embedder.model)
    threshold = cfg.thresholds.dedup_distance or profile.dedup_distance
    embedder = make_embedder(cfg.embedder.provider, cfg.embedder.model)

    scope_dirs = {
        paths.global_memory_dir(): paths.global_memory_dir() / "archive.db",
        paths.project_memory_dir(): paths.project_memory_dir() / "archive.db",
    }
    for scope_dir, db in scope_dirs.items():
        scope_dir.mkdir(parents=True, exist_ok=True)
        try:
            archive.init(
                db,
                embedder_name=embedder.name,
                model=cfg.embedder.model,
                dim=embedder.dim,
                distance=embedder.distance,
            )
        except archive.EmbedderMismatch as e:
            LOGGER.error("embedder mismatch in %s — re-index required: %s", db, e)
            return

    for d in decisions:
        action = d.get("action")
        scope = d.get("scope", "project")
        scope_dir = (
            paths.global_memory_dir() if scope == "global" else paths.project_memory_dir()
        )
        db = scope_dir / "archive.db"

        # The curator prompt calls a memory's filename `name` and its body
        # `content` (and its category `type`). Tolerate both the prompt's
        # documented shape and the older `slug`/`text`/`kind` shape so old
        # tests and any external callers keep working.
        slug = d.get("slug") or _normalise_slug(d.get("name"))
        text = d.get("text") or d.get("content")
        kind = d.get("kind") or d.get("type")

        if action in ("write_md", "update_md"):
            if not slug or not text:
                LOGGER.warning(
                    "curator: dropping %s with missing name/content: %s",
                    action,
                    {k: v for k, v in d.items() if k not in ("text", "content")},
                )
                continue
            [vec] = embedder.embed([text])
            dup_slug, dist = dedup.find_dup_slug(db=db, embedding=vec, threshold=threshold)
            if dup_slug:
                LOGGER.info("dedup: %r -> %r (distance=%.3f)", slug, dup_slug, dist)
                slug = dup_slug
                provenance: versioning.Provenance = "dedup"
            else:
                LOGGER.info("dedup-miss: nearest md distance=%s", dist)
                provenance = action  # "write_md" or "update_md"

            # Snapshot the prior body's text before writing so we can detect a
            # body change and emit a supersedes edge afterward.
            prior_text = _read_live_text(db, slug)

            versioning.snapshot_then_replace(
                db, scope_dir=scope_dir, slug=slug,
                new_text=text, new_kind=kind or "reference",
                new_embedding=vec, provenance=provenance,
            )

            # Emit edges: supersedes (auto) + related (from curator JSON).
            _emit_edges_after_write(
                db=db,
                slug=slug,
                new_text=text,
                prior_text=prior_text,
                edge_specs=d.get("edges", []),
            )

        elif action in ("insert_archive", "archive_turn"):
            # Turn entries are ephemeral and not md-backed — no versioning, no dedup.
            if not text:
                LOGGER.warning("curator: dropping %s with missing content", action)
                continue
            [vec] = embedder.embed([text])
            archive.insert_entry(
                db,
                text=text,
                kind=kind or "note",
                source=d.get("source", "turn"),
                pinned=False,
                embedding=vec,
            )

        elif action == "skip_all":
            LOGGER.info("curator: skip_all (%s)", d.get("reason", ""))

        else:
            LOGGER.info("curator: ignoring decision with action=%r", action)


def _normalise_slug(name: str | None) -> str | None:
    """Ensure a slug ends with `.md`. Haiku returns bare names per the prompt."""
    if not name:
        return None
    return name if name.endswith(".md") else f"{name}.md"


def _iter_turns(transcript_path: str) -> Iterator[tuple[str, str]]:
    """Yield (role, text) for each user/assistant/compaction/subagent_stop event.

    Roles beyond user/assistant:
      - "compaction"     — {"type": "summary", "summary": "..."} events
      - "subagent_stop"  — {"type": "subagent_stop", "summary": "..."} events

    Ported from memory-tools/curator-worker.py. Handles:
    - string content
    - list-of-parts content (extracts type=text parts, skips tool_use/tool_result)
    - malformed lines (logged-and-skipped, not raised)
    """
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev_type = ev.get("type")
                if ev_type == "summary":
                    summary_text = ev.get("summary", "")
                    if summary_text:
                        yield "compaction", summary_text
                    continue
                if ev_type == "subagent_stop":
                    summary_text = ev.get("summary", "")
                    if summary_text:
                        yield "subagent_stop", summary_text
                    continue
                msg = ev.get("message") or {}
                role = msg.get("role")
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [
                        c.get("text", "")
                        for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    text = "\n".join(parts)
                if not text.strip():
                    continue
                yield role, text
    except OSError as e:
        LOGGER.warning("transcript read failed: %s", e)


def _parse_full_transcript(transcript_path: str) -> str:
    """Concatenate all user/assistant turns with <USER>/<ASSISTANT> tags.

    Tail-truncates when the result would exceed MAX_TRANSCRIPT_CHARS.
    """
    chunks: list[str] = []
    for role, text in _iter_turns(transcript_path):
        label = "USER" if role == "user" else "ASSISTANT"
        chunks.append(f"<{label}>\n{text}\n</{label}>")
    full = "\n\n".join(chunks)
    if len(full) > MAX_TRANSCRIPT_CHARS:
        full = "...(earlier turns truncated)...\n\n" + full[-MAX_TRANSCRIPT_CHARS:]
    return full


def _read_conversation_tail() -> str:
    """Read the conversation tail for the curator.

    Prefers ``CLAUDE_ALMANAC_TRANSCRIPT`` (explicit override for CLI/testing),
    falls back to ``CLAUDE_ALMANAC_HOOK_TRANSCRIPT`` (set by the Stop hook
    when forking the worker). Returns empty string if neither is set or
    the path doesn't exist.
    """
    for env_var in ("CLAUDE_ALMANAC_TRANSCRIPT", "CLAUDE_ALMANAC_HOOK_TRANSCRIPT"):
        path = os.environ.get(env_var)
        if path and Path(path).exists():
            return _parse_full_transcript(path)
    return ""


def _recover_unescaped_quotes(raw: str) -> str | None:
    """Repair JSON payloads where the LLM emitted unescaped `"` inside
    string values. Returns a candidate repaired string, or None when the
    input looks too malformed to bother with.

    Heuristic: walk the raw text, track whether we're inside a string,
    and escape any `"` that can't plausibly terminate the current string
    (because the next non-whitespace char isn't a valid JSON
    structural token: `,`, `}`, `]`, `:`). Conservative by design — if
    the next char IS structural, the quote is treated as a genuine
    terminator. This catches the common gemma failure mode
    (`"content": "...\"Engineer's Ops Console\" aesthetic..."`) without
    needing an LLM round-trip.
    """
    if not raw or raw.count('"') < 2:
        return None
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\" and in_string:
            out.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            if not in_string:
                out.append(ch)
                in_string = True
                i += 1
                continue
            # Peek forward past whitespace to classify this quote.
            j = i + 1
            while j < n and raw[j] in " \t\r\n":
                j += 1
            nxt = raw[j] if j < n else ""
            if nxt in (",", "}", "]", ":", ""):
                # Structural terminator — genuine string close.
                out.append(ch)
                in_string = False
                i += 1
                continue
            # Unescaped inner quote — escape it.
            out.append("\\")
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    if in_string:
        # Unbalanced — don't return a half-repaired string.
        return None
    repaired = "".join(out)
    return repaired if repaired != raw else None


def _strip_json_fence(raw: str) -> str:
    """Strip a ```json ... ``` (or bare ```) markdown fence from Haiku output.

    Haiku occasionally wraps its JSON decision payload in a code fence even
    when the prompt asks for raw JSON. Stripping here lets the parser accept
    the fenced form without losing the payload.
    """
    s = raw.strip()
    if not s.startswith("```"):
        return s
    # Drop opening fence line (```json / ```)
    first_newline = s.find("\n")
    if first_newline == -1:
        return s
    inner = s[first_newline + 1 :]
    if inner.rstrip().endswith("```"):
        inner = inner.rstrip()
        inner = inner[: -len("```")]
    return inner.strip()


def _parse_decisions(raw: str) -> list[dict[str, Any]]:
    """Parse Haiku's decision payload, tolerating observed shapes.

    Has been seen to return any of:
      - `{"decisions": [ ... ]}` — the documented contract
      - `[ ... ]`                — a bare list of decisions
      - ````json\n...\n````      — any of the above wrapped in a code fence
      - JSON with unescaped `"` inside string values — recovered via
        _recover_unescaped_quotes (v0.3.10, belt-and-braces for Ollama <
        grammar-constrained or for providers without schema enforcement)

    Returns the decision list, or [] if the payload is unparseable or empty.
    Never raises — caller (main) relies on a clean list contract.
    """
    cleaned = _strip_json_fence(raw)
    if not cleaned:
        return []
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as primary_exc:
        # v0.3.10: retry after auto-escaping suspect inner quotes before giving up.
        recovered = _recover_unescaped_quotes(cleaned)
        if recovered is not None:
            try:
                payload = json.loads(recovered)
                LOGGER.info(
                    "curator: recovered from unescaped-quote payload (len=%d)",
                    len(raw),
                )
            except json.JSONDecodeError:
                LOGGER.warning(
                    "curator: LLM returned non-JSON (len=%d, err=%s): %s",
                    len(raw), primary_exc, raw,
                )
                return []
        else:
            LOGGER.warning(
                "curator: LLM returned non-JSON (len=%d, err=%s): %s",
                len(raw), primary_exc, raw,
            )
            return []
    if isinstance(payload, list):
        return [d for d in payload if isinstance(d, dict)]
    if isinstance(payload, dict):
        decisions = payload.get("decisions", [])
        if isinstance(decisions, list):
            return [d for d in decisions if isinstance(d, dict)]
    LOGGER.warning("curator: unexpected payload shape: %s", type(payload).__name__)
    return []


def main() -> None:
    _setup_logging()
    tail = _read_conversation_tail()
    if not tail.strip():
        LOGGER.info("curator: no conversation tail, skipping")
        return
    try:
        raw = _run_llm(tail)
        decisions = _parse_decisions(raw)
        if decisions:
            _apply_decisions(decisions)
    except Exception:
        LOGGER.exception("curator main loop failed")


if __name__ == "__main__":
    main()
